#!/usr/bin/env python3
"""Import a document directory, verify a candidate index, then publish it locally."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from llama_index.core import Document
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.vector_stores.types import VectorStoreQuery
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from reconcile import reconcile
import operations

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "qdrant_export", ROOT / "adapters/index/qdrant_export.py"
)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
DIMENSIONS = 256
VECTOR_NAME = "lexical"


class LexicalEmbedding(BaseEmbedding):
    """Signed token hashing for offline lexical search, not semantic embeddings."""

    model_name: str = "local-token-hash-v1"

    def _get_text_embedding(self, text):
        vector = [0.0] * DIMENSIONS
        for token in re.findall(r"\w+", text.casefold()):
            digest = hashlib.sha256(token.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % DIMENSIONS] += (
                1 if digest[4] & 1 else -1
            )
        return vector

    def _get_query_embedding(self, query):
        return self._get_text_embedding(query)

    async def _aget_query_embedding(self, query):
        return self._get_query_embedding(query)


def save_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def node_id(index, document):
    identity = [
        document.metadata["tenant"],
        document.id_,
        document.metadata["revision"],
        index,
    ]
    return str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(identity)))


def read_source(source):
    """Read only supported document files, with the same bounds for every runner."""
    if not source.is_dir():
        raise ValueError("Source must be a directory of UTF-8 .md or .txt files")
    count = 0
    total_bytes = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(
                "Source symlinks are not supported; use a dedicated snapshot directory"
            )
        if not path.is_file() or path.suffix.lower() not in (".txt", ".md"):
            continue
        with path.open("rb") as stream:
            content = stream.read(8 * 1024 * 1024 + 1)
        total_bytes += len(content)
        if (
            len(content) > 8 * 1024 * 1024
            or total_bytes > 32 * 1024 * 1024
            or count >= 1000
        ):
            raise ValueError(
                "Example limit: 1,000 documents, 8 MiB per file, 32 MiB total"
            )
        count += 1
        yield exporter.identifier(path.relative_to(source).as_posix()), content


def prepare(source, tenant, generation):
    """Snapshot file bytes once; the returned nodes are exactly what gets written."""
    exporter.identifier(tenant)
    documents = []
    for document_id, content in read_source(source):
        metadata = {"tenant": tenant, "revision": hashlib.sha256(content).hexdigest()}
        documents.append(
            Document(
                id_=document_id,
                text=content.decode("utf-8"),
                metadata=metadata,
                excluded_embed_metadata_keys=list(metadata),
                excluded_llm_metadata_keys=list(metadata),
            )
        )
    splitter = SentenceSplitter(
        chunk_size=128,
        chunk_overlap=16,
        tokenizer=str.split,
        chunking_tokenizer_fn=lambda text: re.split(r"(?<=[.!?])\s+", text),
        id_func=node_id,
        include_prev_next_rel=False,
    )
    nodes = IngestionPipeline(transformations=[splitter], disable_cache=True).run(
        documents=documents
    )
    chunks = {d.id_: [] for d in documents}
    for node in nodes:
        node.metadata["chunk_id"] = node.id_
        node.excluded_embed_metadata_keys.append("chunk_id")
        chunks[node.ref_doc_id].append(node.id_)
    rows = [
        {
            "tenant": tenant,
            "document_id": d.id_,
            "state": "present",
            "settled": True,
            "revision": d.metadata["revision"],
            "expected_chunks": chunks[d.id_],
            "job_id": generation,
        }
        for d in documents
    ]
    rows.sort(key=lambda row: (row["tenant"], row["document_id"]))
    return nodes, rows


def selected_collection(client, alias):
    return next(
        (
            a.collection_name
            for a in client.get_aliases().aliases
            if a.alias_name == alias
        ),
        None,
    )


def verify_exports(wraith, manifest, inventory, output):
    """Default native verifier; the study supplies a separately labeled reference."""
    with (output / "check.log").open("x", encoding="utf-8") as log:
        check = subprocess.run(
            [
                str(wraith),
                "index",
                "check",
                "--manifest",
                str(manifest),
                "--inventory",
                str(inventory),
                "--json",
                str(output / "report.json"),
                "--html",
                str(output / "report.html"),
            ],
            stdout=log,
            stderr=log,
            timeout=60,
        )
    return check.returncode


def publish(
    client,
    source,
    alias,
    output,
    wraith,
    *,
    tenant="docs",
    compare_plain=False,
    _verifier=None,
):
    """Single local owner: caller holds Qdrant's persistent-directory lock.

    No old collection is modified or removed. A failed attempt is never resumed.
    A new invocation creates a new generation and preserves the incomplete one.
    """
    exporter.identifier(alias)
    verifier_name, verifier = _verifier or ("wraith", verify_exports)
    if (
        verifier_name not in ("wraith", "plain-reference-v1")
        or (_verifier is not None and verifier_name != "plain-reference-v1")
        or not callable(verifier)
    ):
        raise ValueError("Unsupported verifier")
    if _verifier is None:
        wraith = Path(wraith).resolve(strict=True)
    if any(c.name == alias for c in client.get_collections().collections):
        raise ValueError("Serving alias conflicts with an existing collection name")
    output.mkdir(parents=True, exist_ok=False)
    generation = "wraith-" + uuid.uuid4().hex
    previous = selected_collection(client, alias)
    phase = "prepare"
    started = time.perf_counter()
    try:
        save_json(
            output / "job.json",
            {
                "schema_version": 1,
                "generation": generation,
                "alias": alias,
                "verifier": verifier_name,
                "previous_collection": previous,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        nodes, rows = prepare(source, tenant, generation)
        header = {
            "schema_version": 1,
            "kind": "manifest",
            "scope": f"local/{alias}",
            "generation": generation,
            "stable": True,
            "complete": True,
            "record_count": len(rows),
        }
        manifest = output / "manifest.jsonl"
        with manifest.open("x", encoding="utf-8") as stream:
            for row in [header, *rows]:
                stream.write(json.dumps(row) + "\n")
        # The authoritative manifest is closed before the first vector-store write.
        phase = "ingest"
        client.create_collection(
            generation,
            vectors_config={
                VECTOR_NAME: models.VectorParams(
                    size=DIMENSIONS,
                    distance=models.Distance.COSINE,
                )
            },
        )
        store = QdrantVectorStore(
            client=client,
            collection_name=generation,
            dense_vector_name=VECTOR_NAME,
            index_doc_id=False,
        )
        IngestionPipeline(
            transformations=[LexicalEmbedding()],
            vector_store=store,
            disable_cache=True,
        ).run(nodes=nodes)
        ingestion_seconds = time.perf_counter() - started
        phase = "export"
        began = time.perf_counter()
        inventory = output / "inventory.jsonl"
        scan = exporter.export_inventory(
            client, generation, header, inventory, quiesced=True
        )
        export_seconds = time.perf_counter() - began
        phase = "verify"
        began = time.perf_counter()
        # Logs stay beside reports; do not include environment or private paths in receipts.
        check_exit = verifier(wraith, manifest, inventory, output)
        check_seconds = time.perf_counter() - began
        result = {
            "schema_version": 1,
            "generation": generation,
            "previous_collection": previous,
            "alias": alias,
            "exit_code": check_exit,
            "verifier": verifier_name,
            "export": scan,
            "documents": len(rows),
            "chunks": len(nodes),
            "provider_calls": 0,
            "seconds": {
                "prepare_and_ingest": ingestion_seconds,
                "export": export_seconds,
                (
                    "wraith_check_with_reports"
                    if verifier_name == "wraith"
                    else "plain_check_json_only"
                ): check_seconds,
            },
        }
        result["evidence_sha256"] = {
            name: operations.digest(output / name)
            for name in ("job.json", "manifest.jsonl", "inventory.jsonl", "report.json")
            if (output / name).is_file()
        }
        if compare_plain:
            began = time.perf_counter()
            plain = reconcile(manifest, inventory)
            result["seconds"]["plain_in_process_no_html"] = time.perf_counter() - began
            save_json(output / "plain.json", plain)
            result["plain_exit_code"] = plain["exit_code"]
        save_json(output / "verification.json", result)
        if check_exit != 0:
            return result
        if compare_plain and plain["exit_code"] != check_exit:
            raise ValueError("Comparator disagreement; inspect the preserved evidence")
        # Another writer is unsupported. This check is diagnostic, not a distributed CAS.
        phase = "promote"
        if selected_collection(client, alias) != previous:
            raise ValueError(
                "Serving alias changed during ingestion; candidate was not promoted"
            )
        alias_operations = []
        if previous is not None:
            alias_operations.append(
                models.DeleteAliasOperation(
                    delete_alias=models.DeleteAlias(alias_name=alias)
                )
            )
        alias_operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=generation,
                    alias_name=alias,
                )
            )
        )
        client.update_collection_aliases(change_aliases_operations=alias_operations)
        if selected_collection(client, alias) != generation:
            raise RuntimeError("Alias promotion could not be confirmed")
        save_json(
            output / "promotion.json",
            {
                "schema_version": 1,
                "alias": alias,
                "collection": generation,
                "previous_collection": previous,
            },
        )
        return result
    except BaseException as error:
        # A crash after alias publication can leave no receipt: the actual alias is authoritative.
        save_json(
            output / "error.json",
            {
                "schema_version": 1,
                "phase": phase,
                "error_type": type(error).__name__,
                "generation": generation,
                "previous_collection": previous,
                "next_action": {
                    "prepare": "Check source encoding, symlinks and documented size limits.",
                    "ingest": "Inspect the candidate collection; start a new attempt after fixing ingestion.",
                    "export": "Check candidate payload identities and exporter limits.",
                    "verify": "Read check.log and reports; verification did not authorize promotion.",
                    "promote": "Inspect the actual serving alias before taking further action.",
                }[phase],
            },
        )
        raise


def search(client, alias, query):
    if selected_collection(client, alias) is None:
        raise ValueError("No serving index; run ingest successfully first")
    store = QdrantVectorStore(
        client=client, collection_name=alias, dense_vector_name=VECTOR_NAME
    )
    result = store.query(
        VectorStoreQuery(
            query_embedding=LexicalEmbedding().get_query_embedding(query),
            similarity_top_k=3,
        )
    )
    return [
        {"document": n.ref_doc_id, "text": n.text, "score": score}
        for n, score in zip(result.nodes, result.similarities)
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, required=True, help="Dedicated local Qdrant directory"
    )
    parser.add_argument("--alias", default="documents")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--source", type=Path, required=True)
    ingest.add_argument(
        "--output", type=Path, required=True, help="New evidence directory"
    )
    ingest.add_argument("--wraith", type=Path, required=True)
    ingest.add_argument("--compare-plain", action="store_true")
    inspection = commands.add_parser(
        "inspect", help="Read recovery evidence and plan retention; never deletes"
    )
    inspection.add_argument("--history", type=Path, required=True)
    inspection.add_argument("--keep-previous", type=int, default=1)
    inspection.add_argument("--json", type=Path, help="New JSON evidence file")
    inspection.add_argument("--output", choices=["human", "json"], default="human")
    commands.add_parser("status", help="Inspect the authoritative serving alias")
    query = commands.add_parser("query")
    query.add_argument("text")
    args = parser.parse_args()
    try:
        if args.command != "ingest" and not args.db.is_dir():
            raise ValueError("Local database does not exist; run ingest first")
        with closing(QdrantClient(path=str(args.db))) as client:
            if args.command == "inspect":
                result = operations.inspect(
                    client, args.history, args.alias, args.keep_previous
                )
                if args.json:
                    save_json(args.json, result)
                print(
                    json.dumps(result, indent=2)
                    if args.output == "json"
                    else operations.human(result)
                )
                return 0 if result["inspection_complete"] else 3
            if args.command == "status":
                print(
                    json.dumps(
                        {
                            "alias": args.alias,
                            "collection": selected_collection(client, args.alias),
                        }
                    )
                )
                return 0
            if args.command == "query":
                print(json.dumps(search(client, args.alias, args.text), indent=2))
                return 0
            result = publish(
                client,
                args.source,
                args.alias,
                args.output,
                args.wraith,
                compare_plain=args.compare_plain,
            )
            print(json.dumps(result, indent=2))
            return (
                result["exit_code"] if result["exit_code"] in (0, 1, 2, 3, 130) else 2
            )
    except KeyboardInterrupt:
        return 130
    except operations.EvidenceError as error:
        print(f"Inspection failed: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(
            f"Command failed ({type(error).__name__}); inspect the evidence and serving alias.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
