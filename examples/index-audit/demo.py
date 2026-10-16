#!/usr/bin/env python3
"""Local Qdrant demonstration: partial write and missed deletion, then repair.

These are deliberate controls against a real local client backend, not newly
found upstream bugs, live model evaluations, or customer evidence.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "qdrant_export", ROOT / "adapters/index/qdrant_export.py"
)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wraith", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from qdrant_client import QdrantClient, models

    args.output.mkdir(parents=True, exist_ok=False)
    client = QdrantClient(":memory:")
    collection = "wraith-demo"
    client.create_collection(
        collection,
        vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE),
    )
    header = {
        "schema_version": 1,
        "kind": "manifest",
        "scope": "demo/support",
        "generation": "job-42",
        "stable": True,
        "complete": True,
        "record_count": 2,
    }
    manifest = [
        {
            "tenant": "demo",
            "document_id": "policy",
            "state": "present",
            "settled": True,
            "revision": "8",
            "expected_chunks": ["0", "1", "2"],
            "job_id": "ingest-42",
        },
        {
            "tenant": "demo",
            "document_id": "retired",
            "state": "deleted",
            "settled": True,
            "job_id": "delete-41",
        },
    ]
    path = args.output / "manifest.jsonl"
    path.write_text(
        "\n".join(json.dumps(x) for x in [header, *manifest]) + "\n", encoding="utf-8"
    )

    def point(document, chunk):
        return models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"wraith-demo/{document}/{chunk}")),
            vector=[1.0, 0.0, 0.0],
            payload={
                "tenant": "demo",
                "document_id": document,
                "chunk_id": chunk,
                "revision": "8",
            },
        )

    client.upsert(
        collection,
        points=[point("policy", "0"), point("policy", "2"), point("retired", "0")],
        wait=True,
    )
    results = []
    try:
        for name, expected_exit in [("before", 1), ("after", 0)]:
            if name == "after":
                client.upsert(collection, points=[point("policy", "1")], wait=True)
                client.delete(
                    collection,
                    points_selector=models.PointIdsList(
                        points=[point("retired", "0").id]
                    ),
                    wait=True,
                )
            inventory = args.output / f"{name}.jsonl"
            stats = exporter.export_inventory(
                client, collection, header, inventory, quiesced=True
            )
            result = subprocess.run(
                [
                    str(args.wraith.resolve()),
                    "index",
                    "check",
                    "--manifest",
                    str(path),
                    "--inventory",
                    str(inventory),
                    "--json",
                    str(args.output / f"{name}.json"),
                    "--html",
                    str(args.output / f"{name}.html"),
                    "--output",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != expected_exit:
                raise RuntimeError(
                    f"{name}: expected exit {expected_exit}, got {result.returncode}: {result.stderr}"
                )
            report = json.loads(result.stdout)
            assert report["summary"]["failed"] == (2 if name == "before" else 0)
            results.append(
                {
                    "phase": name,
                    "exit_code": result.returncode,
                    "counts": report["summary"],
                    "export": stats,
                }
            )
    finally:
        client.close()
    summary = {
        "kind": "controlled local Qdrant demonstration",
        "provider_calls": 0,
        "results": results,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
