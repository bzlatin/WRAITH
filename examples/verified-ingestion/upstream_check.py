#!/usr/bin/env python3
"""Check the pinned upstream Qdrant recipe through its public transformation hook.

Preparation downloads only source and license. Execution is offline, uses an owned
in-memory database, and replaces provider transforms with deterministic local ones.
"""

import argparse
import ast
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import socket
import sys
import time
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "adapters/index"))
COMMIT = "619d74664e8404612038bc15a1a40c686037277c"
SOURCE = (
    "docs/src/content/docs/framework/module_guides/loading/ingestion_pipeline/index.md"
)
DIGEST = "2d66879a7aeece066dc782d3e1029d4af957547a91df50218d539c5831a7b31c"
LICENSE_DIGEST = "24f40b5190fdacabc24ddbb5f76364d15e4f030925220ea300d8a2dd4993c8cb"
URL = f"https://raw.githubusercontent.com/run-llama/llama_index/{COMMIT}/"


def prepare(destination):
    # Validate both downloads before creating any fixture files. Never execute them.
    files = {}
    for remote, name, digest in (
        (SOURCE, "pipeline.md", DIGEST),
        ("LICENSE", "LICENSE", LICENSE_DIGEST),
    ):
        with urllib.request.urlopen(URL + remote, timeout=30) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Upstream source/license checksum mismatch")
        files[name] = data
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        (destination / name).write_bytes(data)


def constructor(source):
    data = (source / "pipeline.md").read_bytes()
    if hashlib.sha256(data).hexdigest() != DIGEST:
        raise ValueError("Upstream source checksum mismatch")
    if hashlib.sha256((source / "LICENSE").read_bytes()).hexdigest() != LICENSE_DIGEST:
        raise ValueError("Upstream license checksum mismatch")
    section = data.decode().split("## Connecting to Vector Databases\n", 1)[1]
    code = re.search(r"```python\n(.*?)```", section, re.S).group(1)
    tree = ast.parse(code)
    assignments = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "pipeline" for t in n.targets)
    ]
    if len(assignments) != 1:
        raise ValueError("Pinned upstream constructor changed")
    return ast.fix_missing_locations(ast.Module(body=assignments, type_ignores=[]))


def run(args):
    # Optional SDK imports belong only to execution, not preparation/tooling tests.
    from llama_index.core import Document
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.schema import TransformComponent
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from qdrant_client import QdrantClient
    from llamaindex_manifest import ManifestCapture, attach_capture
    import qdrant_export
    from reconcile import reconcile
    from search import LexicalEmbedding, save_json, verify_exports

    tree = constructor(args.upstream)
    wraith = args.wraith.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=False)
    save_json(
        args.output / "protocol.json",
        {
            "schema_version": 1,
            "source_url": f"https://github.com/run-llama/llama_index/blob/{COMMIT}/{SOURCE}",
            "source_sha256": DIGEST,
            "steps": ["initial", "repeat", "revision", "rename"],
            "expected_exit_codes": [0, 0, 0, 0],
            "classification": "upstream recipe compatibility, not independent adoption",
            "substitutions": [
                "local title passthrough",
                "lexical embeddings",
                "word tokenizer",
            ],
            "comparison": "identical exports; Wraith JSON/HTML vs trusted-input script JSON",
        },
    )

    class LocalTitle(TransformComponent):
        def __call__(self, nodes, **kwargs):
            return nodes

    # Freeze inputs before either checker. These ordinary source changes introduce no faults.
    texts = {
        "refunds.md": "Refunds go to the original payment method. " * 15,
        "security.md": "Enable two factor authentication for security. " * 15,
    }
    results = []
    try:
        with (
            closing(QdrantClient(location=":memory:")) as client,
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("Offline execution only"),
            ),
        ):
            for step in ("initial", "repeat", "revision", "rename"):
                if step == "revision":
                    texts["refunds.md"] += " A receipt is required."
                if step == "rename":
                    texts["account-security.md"] = texts.pop("security.md")
                output = args.output / step
                output.mkdir()
                store = QdrantVectorStore(client=client, collection_name=step)
                namespace = {
                    "IngestionPipeline": IngestionPipeline,
                    "SentenceSplitter": lambda **kw: SentenceSplitter(
                        **kw,
                        tokenizer=str.split,
                        chunking_tokenizer_fn=lambda text: re.split(
                            r"(?<=[.!?])\s+", text
                        ),
                    ),
                    "TitleExtractor": LocalTitle,
                    "OpenAIEmbedding": LexicalEmbedding,
                    "vector_store": store,
                }
                # Execute only the hash-pinned constructor assignment, not imports,
                # notebook commands, provider calls, environment setup, or query code.
                exec(compile(tree, "pinned-upstream-constructor", "exec"), namespace)
                pipeline = namespace["pipeline"]
                pipeline.disable_cache = True
                revisions = {
                    name: hashlib.sha256(text.encode()).hexdigest()
                    for name, text in texts.items()
                }
                manifest = output / "manifest.jsonl"
                attach_capture(
                    pipeline,
                    ManifestCapture(
                        destination=str(manifest),
                        scope="upstream-recipe",
                        generation=step,
                        tenant="docs",
                        revisions=revisions,
                    ),
                )
                writes = []
                original = client.upload_points

                def witnessed_write(*positional, **keywords):
                    # Independent assertion at actual storage write, not pipeline return.
                    saved = [
                        json.loads(line) for line in manifest.read_text().splitlines()
                    ]
                    if {d["document_id"] for d in saved[1:]} != set(texts):
                        raise AssertionError("Pre-write source coverage differs")
                    writes.append(True)
                    return original(*positional, **keywords)

                with patch.object(client, "upload_points", side_effect=witnessed_write):
                    pipeline.run(
                        documents=[
                            Document(id_=name, text=text)
                            for name, text in texts.items()
                        ]
                    )
                if not writes:
                    raise AssertionError("No actual vector writes witnessed")
                inventory = output / "inventory.jsonl"
                qdrant_export.export_inventory(
                    client,
                    step,
                    qdrant_export.read_header(manifest),
                    inventory,
                    quiesced=True,
                )
                start = time.perf_counter()
                native = verify_exports(wraith, manifest, inventory, output)
                native_seconds = time.perf_counter() - start
                start = time.perf_counter()
                plain = reconcile(manifest, inventory)
                plain_seconds = time.perf_counter() - start
                save_json(output / "plain.json", plain)
                row = {
                    "step": step,
                    "wraith_exit": native,
                    "plain_exit": plain["exit_code"],
                    "prewrite_witness": True,
                    "documents": len(texts),
                    "chunks": client.count(step, exact=True).count,
                    "wraith_seconds_json_html": native_seconds,
                    "plain_seconds_in_process_json": plain_seconds,
                }
                results.append(row)
                if native != 0 or plain["exit_code"] != 0:
                    raise AssertionError(
                        "Checker disagrees with required normal transition"
                    )
        summary = {
            "schema_version": 1,
            "completed": True,
            "source_commit": COMMIT,
            "source_sha256": DIGEST,
            "steps": results,
            "provider_calls": 0,
            "natural_defects_found": 0,
            "shared_requirements": [
                "source revisions and identities",
                "last transformation hook",
                "uncached full rebuild without docstore",
                "isolated collection and visibility barrier",
                "export and evidence storage",
                "caller-owned publication",
            ],
            "decision": "No integration or decision advantage demonstrated; retain utility and pause SaaS expansion",
        }
        save_json(args.output / "summary.json", summary)
        print(json.dumps(summary, indent=2))
    except BaseException as error:
        save_json(
            args.output / "incomplete.json",
            {"error_type": type(error).__name__, "completed_steps": results},
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--wraith", type=Path)
    args = parser.parse_args()
    if args.prepare:
        if args.upstream or args.output or args.wraith:
            parser.error("Use --prepare alone; execution is a separate offline step")
        prepare(args.prepare)
    elif all((args.upstream, args.output, args.wraith)):
        run(args)
    else:
        parser.error("Choose --prepare or all of --upstream, --output and --wraith")


if __name__ == "__main__":
    main()
