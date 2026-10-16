#!/usr/bin/env python3
"""Read Qdrant metadata into Wraith inventory JSONL. Never mutates the collection."""

import argparse
import itertools
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import urlsplit

MAX_LINE = 1024 * 1024
FIELDS = ["tenant", "document_id", "chunk_id", "revision"]


def identifier(value):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > 1024:
        raise ValueError(
            "Missing or invalid identity metadata; no complete export was saved"
        )
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
        raise ValueError("Identity metadata contains control characters")
    return value


def read_header(path):
    with Path(path).open("rb") as stream:
        line = stream.readline(MAX_LINE + 1)
    if len(line) > MAX_LINE:
        raise ValueError("Manifest header exceeds 1 MiB")
    header = json.loads(line)
    if header.get("schema_version") != 1 or header.get("kind") != "manifest":
        raise ValueError("Expected manifest schema 1")
    for key in ("scope", "generation"):
        identifier(header.get(key))
    for key in ("stable", "complete"):
        if type(header.get(key)) is not bool:
            raise ValueError("Manifest header needs explicit complete/stable flags")
    return header


def export_inventory(
    client, collection, header, destination, *, quiesced=False, max_points=1_000_000
):
    """Caller must freeze source and collection throughout the paired exports.

    Equal counts alone do not establish a snapshot. quiesced is an explicit caller
    attestation, never inferred from two reads or a successful ingestion response.
    Disk spooling avoids retaining the entire collection in Python memory.
    """
    if max_points < 1:
        raise ValueError("max_points must be positive")
    destination = Path(destination)
    if destination.exists():
        raise ValueError(
            "Choose a new inventory path; existing evidence is never overwritten"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wraith-index-") as work:
        db = sqlite3.connect(str(Path(work) / "sort.sqlite"))
        try:
            db.execute(
                "CREATE TABLE chunks(point_id TEXT PRIMARY KEY, tenant TEXT, document_id TEXT, chunk_id TEXT, revision TEXT)"
            )
            before = client.count(collection_name=collection, exact=True).count
            if before > max_points:
                raise ValueError(
                    "Collection exceeds max_points; partition the collection or increase the explicit limit"
                )
            offset = None
            total = 0
            requests = 2  # exact counts before and after the scan
            while True:
                requests += 1
                points, next_offset = client.scroll(
                    collection_name=collection,
                    offset=offset,
                    limit=512,
                    with_payload=FIELDS,
                    with_vectors=False,
                )
                if not points and next_offset is not None:
                    raise ValueError(
                        "Pagination made no progress; no complete export was saved"
                    )
                for point in points:
                    total += 1
                    if total > max_points:
                        raise ValueError(
                            "Scan exceeded max_points; no complete export was saved"
                        )
                    payload = point.payload or {}
                    tenant, doc, chunk = (
                        identifier(payload.get(k)) for k in FIELDS[:3]
                    )
                    revision = payload.get("revision")
                    if revision is not None:
                        identifier(revision)
                    db.execute(
                        "INSERT INTO chunks VALUES(?,?,?,?,?)",
                        (str(point.id), tenant, doc, chunk, revision),
                    )
                if next_offset is None:
                    break
                offset = next_offset
            after = client.count(collection_name=collection, exact=True).count
            if before != total or after != total:
                raise ValueError(
                    "Point counts changed or pagination was incomplete; freeze writes and export again"
                )
            db.execute(
                "CREATE INDEX document_order ON chunks(tenant, document_id, chunk_id)"
            )
            count = db.execute(
                "SELECT count(*) FROM (SELECT tenant, document_id FROM chunks GROUP BY tenant, document_id)"
            ).fetchone()[0]
            inventory_header = {
                "schema_version": 1,
                "kind": "inventory",
                "scope": header["scope"],
                "generation": header["generation"],
                "complete": True,
                "stable": bool(quiesced and header["stable"]),
                "record_count": count,
            }
            # Same-directory temporary file plus exclusive hard-link publication.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=".inventory-",
                delete=False,
            ) as output:
                temporary = Path(output.name)
                try:
                    output.write(json.dumps(inventory_header) + "\n")
                    rows = db.execute(
                        "SELECT tenant, document_id, chunk_id, revision FROM chunks ORDER BY tenant, document_id, chunk_id"
                    )
                    for (tenant, document), group in itertools.groupby(
                        rows, key=lambda r: r[:2]
                    ):
                        chunks = []
                        previous = None
                        size = 0
                        for _, _, chunk, revision in group:
                            if previous == chunk:
                                raise ValueError(
                                    "Multiple points share the same document/chunk identity"
                                )
                            previous = chunk
                            value = {"id": chunk, "revision": revision}
                            size += len(json.dumps(value).encode()) + 2
                            if size > MAX_LINE:
                                raise ValueError(
                                    "Document exceeds the 1 MiB record bound; partition its manifest"
                                )
                            chunks.append(value)
                        line = (
                            json.dumps(
                                {
                                    "tenant": tenant,
                                    "document_id": document,
                                    "chunks": chunks,
                                }
                            )
                            + "\n"
                        )
                        if len(line.encode()) > MAX_LINE:
                            raise ValueError("Document exceeds the 1 MiB record bound")
                        output.write(line)
                    output.flush()
                    os.fsync(output.fileno())
                except BaseException:
                    output.close()
                    temporary.unlink(missing_ok=True)
                    raise
            try:
                os.link(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        finally:
            db.close()
    return {
        "points": total,
        "documents": count,
        "read_calls": requests,
        "stable": inventory_header["stable"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-key-env", default="QDRANT_API_KEY")
    parser.add_argument(
        "--quiesced",
        action="store_true",
        help="Attest writes are frozen for both exports; otherwise the audit is inconclusive",
    )
    parser.add_argument("--max-points", type=int, default=1_000_000)
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.username or url.password or url.query or url.fragment:
        parser.error("Put credentials in the named environment variable, not the URL")
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        parser.error("Use HTTPS, or HTTP on loopback for local development")
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            url=args.url, api_key=os.environ.get(args.api_key_env), timeout=15
        )
        try:
            result = export_inventory(
                client,
                args.collection,
                read_header(args.manifest),
                args.output,
                quiesced=args.quiesced,
                max_points=args.max_points,
            )
        finally:
            client.close()
    except Exception as error:
        # SDK errors can contain credentials, URLs, or application content.
        print(
            f"Export failed ({type(error).__name__}); check connectivity, metadata, pagination, and a new output path. Do not treat this attempt as successful.",
            file=__import__("sys").stderr,
        )
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
