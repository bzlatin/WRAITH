"""The comparison verifier must block the frozen workload's incomplete evidence."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/verified-ingestion"
sys.path.insert(0, str(EXAMPLE))
spec = importlib.util.spec_from_file_location(
    "reference_check", EXAMPLE / "reference_check.py"
)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


class ReferenceTests(unittest.TestCase):
    def test_complete_partial_unknown_and_empty_match_frozen_requirements(self):
        for mode, code in (
            ("complete", 0),
            ("partial", 1),
            ("unknown", 3),
            ("empty", 3),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as work:
                root = Path(work)
                header = {
                    "schema_version": 1,
                    "scope": "test",
                    "generation": "test",
                    "stable": True,
                    "complete": True,
                    "record_count": 0 if mode == "empty" else 1,
                }
                manifest = root / "manifest.jsonl"
                inventory = root / "inventory.jsonl"
                planned = [
                    {
                        "tenant": "t",
                        "document_id": "d",
                        "state": "present",
                        "settled": True,
                        "revision": "r",
                        "expected_chunks": ["0", "1"],
                    }
                ]
                chunks = [{"id": "0", "revision": None if mode == "unknown" else "r"}]
                if mode != "partial":
                    chunks.append({"id": "1", "revision": "r"})
                observed = [{"tenant": "t", "document_id": "d", "chunks": chunks}]
                for path, kind, rows in (
                    (manifest, "manifest", planned),
                    (inventory, "inventory", observed),
                ):
                    if mode == "empty":
                        rows = []
                    path.write_text(
                        "\n".join(
                            json.dumps(v) for v in [{**header, "kind": kind}, *rows]
                        )
                        + "\n"
                    )
                self.assertEqual(
                    reference.verify(None, manifest, inventory, root), code
                )
                report = json.loads((root / "report.json").read_text())
                self.assertEqual(
                    report["status"], {0: "passed", 1: "failed", 3: "unknown"}[code]
                )
                self.assertFalse((root / "report.html").exists())
                with self.assertRaises(FileExistsError):
                    reference.verify(None, manifest, inventory, root)


if __name__ == "__main__":
    unittest.main()
