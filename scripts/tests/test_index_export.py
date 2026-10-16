"""Exporter failures must never look like complete inventories. No Qdrant dependency."""

import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "qdrant_export", ROOT / "adapters/index/qdrant_export.py"
)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
HEADER = {"scope": "test", "generation": "g1", "stable": True}


def point(n, **changes):
    payload = {
        "tenant": "test",
        "document_id": f"doc-{n}",
        "chunk_id": str(n),
        "revision": "v1",
    }
    payload.update(changes)
    return SimpleNamespace(id=n, payload=payload)


class Client:
    def __init__(self, pages, before=None, after=None):
        self.pages = list(pages)
        total = sum(len(p[0]) for p in pages)
        self.counts = iter(
            [total if before is None else before, total if after is None else after]
        )
        self.calls = []

    def count(self, **kwargs):
        self.calls.append(("count", kwargs))
        return SimpleNamespace(count=next(self.counts))

    def scroll(self, **kwargs):
        self.calls.append(("scroll", kwargs))
        return self.pages.pop(0)


class ExportTests(unittest.TestCase):
    def test_pages_sorted_and_no_vectors_or_text_requested(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "index.jsonl"
            client = Client([([point(9)], "next"), ([point(1)], None)])
            result = exporter.export_inventory(
                client, "demo", HEADER, path, quiesced=True
            )
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(rows[0]["record_count"], 2)
            self.assertEqual(
                [row["document_id"] for row in rows[1:]], ["doc-1", "doc-9"]
            )
            self.assertEqual(result["read_calls"], 4)
            for method, kwargs in client.calls:
                if method == "scroll":
                    self.assertIs(kwargs["with_vectors"], False)
                    self.assertEqual(kwargs["with_payload"], exporter.FIELDS)

    def test_stability_requires_explicit_attestation(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "index.jsonl"
            exporter.export_inventory(
                Client([([point(1)], None)]), "demo", HEADER, path
            )
            self.assertFalse(json.loads(path.read_text().splitlines()[0])["stable"])

    def test_missing_revision_is_preserved_as_unknown(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "index.jsonl"
            exporter.export_inventory(
                Client([([point(1, revision=None)], None)]), "demo", HEADER, path
            )
            self.assertIsNone(
                json.loads(path.read_text().splitlines()[1])["chunks"][0]["revision"]
            )

    def test_scan_failure_never_publishes_output(self):
        clients = [
            Client([([point(1)], None)], before=2),
            Client([([point(1)], None)], after=2),
            Client([([point(1, tenant=None)], None)]),
            Client([([], "nonempty")], before=1),
            Client([([point(1)], "cycle"), ([point(1)], "cycle")], before=2),
            Client([([point(1), point(2, document_id="doc-1", chunk_id="1")], None)]),
        ]
        for client in clients:
            with self.subTest(client=client), tempfile.TemporaryDirectory() as work:
                path = Path(work) / "index.jsonl"
                with self.assertRaises(Exception):
                    exporter.export_inventory(
                        client, "demo", HEADER, path, quiesced=True
                    )
                self.assertFalse(path.exists())
                self.assertEqual(list(Path(work).iterdir()), [])

    def test_point_cap_and_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "index.jsonl"
            with self.assertRaises(ValueError):
                exporter.export_inventory(
                    Client([([point(1), point(2)], None)]),
                    "demo",
                    HEADER,
                    path,
                    max_points=1,
                )
            self.assertFalse(path.exists())
            path.write_text("original")
            with self.assertRaises(ValueError):
                exporter.export_inventory(Client([]), "demo", HEADER, path)
            self.assertEqual(path.read_text(), "original")

    def test_header_rejects_unknown_schema_and_missing_attestations(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "manifest.jsonl"
            for header in [
                {"schema_version": 2, "kind": "manifest"},
                {"schema_version": 1, "kind": "manifest", **HEADER},
            ]:
                path.write_text(json.dumps(header) + "\n")
                with self.assertRaises(ValueError):
                    exporter.read_header(path)


if __name__ == "__main__":
    unittest.main()
