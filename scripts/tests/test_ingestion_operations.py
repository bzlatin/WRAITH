"""Recovery joins and retention must fail conservatively without any SDK writes."""

import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "operations", ROOT / "examples/verified-ingestion/operations.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


def generation(number):
    return "wraith-" + f"{number:032x}"


class ReadClient:
    # Deliberately provides no mutation methods.
    def __init__(self, numbers=(1, 2, 3)):
        self.numbers = numbers
        self.aliases = [("documents", generation(3))]
        self.change = False
        self.reads = 0

    def get_collections(self):
        return SimpleNamespace(
            collections=[SimpleNamespace(name=generation(n)) for n in self.numbers]
        )

    def get_aliases(self):
        self.reads += 1
        aliases = (
            self.aliases
            if not self.change or self.reads == 1
            else [("documents", generation(2))]
        )
        return SimpleNamespace(
            aliases=[
                SimpleNamespace(alias_name=a, collection_name=c) for a, c in aliases
            ]
        )

    def count(self, collection, exact):
        return SimpleNamespace(count=10)


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.client = ReadClient()

    def save(self, path, value):
        path.write_text(json.dumps(value) + "\n")

    def job(self, number, published=True, code=0, complete=True, previous=None):
        directory = self.root / str(number)
        directory.mkdir()
        common = {
            "schema_version": 1,
            "generation": generation(number),
            "alias": "documents",
            "previous_collection": generation(previous) if previous else None,
        }
        self.save(
            directory / "job.json",
            {**common, "created_at_utc": f"2026-10-15T00:00:0{number}+00:00"},
        )
        if not complete:
            return directory
        headers = {}
        for kind, filename in (
            ("manifest", "manifest.jsonl"),
            ("inventory", "inventory.jsonl"),
        ):
            headers[kind] = {
                "schema_version": 1,
                "kind": kind,
                "scope": "local/documents",
                "generation": generation(number),
                "stable": True,
                "complete": True,
                "record_count": 0,
            }
            self.save(directory / filename, headers[kind])
        self.save(
            directory / "report.json",
            {
                "schema_version": 1,
                **headers,
                "status": "passed" if code == 0 else "failed",
            },
        )
        hashes = {
            name: ops.digest(directory / name)
            for name in ("job.json", "manifest.jsonl", "inventory.jsonl", "report.json")
        }
        self.save(
            directory / "verification.json",
            {**common, "exit_code": code, "evidence_sha256": hashes},
        )
        if published:
            self.save(
                directory / "promotion.json",
                {
                    "schema_version": 1,
                    "collection": generation(number),
                    "alias": "documents",
                    "previous_collection": common["previous_collection"],
                },
            )
        return directory

    def setup_history(self):
        self.job(1)
        self.job(2, previous=1)
        self.job(3, published=False, previous=2)

    def test_missing_receipt_and_retirement_plan_are_read_only(self):
        self.setup_history()
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = ops.inspect(self.client, self.root, "documents")
        self.assertEqual(result["recovery"], "selected_verified_receipt_missing")
        self.assertTrue(result["inspection_complete"])
        self.assertEqual(
            [
                r["collection"]
                for r in result["collections"]
                if r["retention_action"] == "review_retirement"
            ],
            [generation(1)],
        )
        self.assertIn(
            "retained_rollback_generation",
            result["collections"][1]["protection_reasons"],
        )
        self.assertNotIn(
            "retained_rollback_generation",
            result["collections"][2]["protection_reasons"],
        )
        self.assertFalse(result["retention"]["deletion_authorized"])
        self.assertIsNone(result["retention"]["candidate_bytes"])
        self.assertEqual(
            before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        )
        self.assertIn("Do not repeat the import", ops.human(result))

    def test_every_alias_protects_its_collection(self):
        self.setup_history()
        self.client.aliases.append(("archive", generation(1)))
        result = ops.inspect(self.client, self.root, "documents")
        self.assertEqual(result["retention"]["review_candidates"], 0)

    def test_unfinished_job_protects_previous_generation(self):
        self.setup_history()
        self.job(4, published=False, complete=False, previous=1)
        self.client.numbers = (1, 2, 3, 4)
        result = ops.inspect(self.client, self.root, "documents")
        self.assertEqual(result["retention"]["review_candidates"], 0)
        self.assertIn(
            "referenced_by_unfinished_job",
            result["collections"][0]["protection_reasons"],
        )

    def test_changed_report_job_or_future_schema_blocks_all_retirement(self):
        for field in ("report.json", "job.json", "verification.json"):
            with self.subTest(field=field):
                self.setup_history()
                path = self.root / "3" / field
                data = json.loads(path.read_text())
                if field == "report.json":
                    data["status"] = "failed"
                elif field == "job.json":
                    data["created_at_utc"] = "2020-01-01T00:00:00+00:00"
                else:
                    data["schema_version"] = 2
                self.save(path, data)
                result = ops.inspect(self.client, self.root, "documents")
                self.assertFalse(result["inspection_complete"])
                self.assertEqual(result["retention"]["review_candidates"], 0)
                if field == "report.json":
                    self.assertIn("report.json", result["issues"][0]["detail"])
                for d in self.root.iterdir():
                    for p in d.iterdir():
                        p.unlink()
                    d.rmdir()

    def test_unknown_collection_and_blocked_candidate_are_kept(self):
        self.setup_history()
        self.job(4, published=False, code=1)
        self.client.numbers = (1, 2, 3, 4, 5)
        rows = ops.inspect(self.client, self.root, "documents")["collections"]
        self.assertEqual(rows[3]["evidence_state"], "gate_blocked")
        self.assertEqual(rows[3]["retention_action"], "keep")
        self.assertEqual(rows[4]["evidence_state"], "untracked")
        self.assertEqual(rows[4]["retention_action"], "keep")

    def test_changed_alias_duplicate_or_legacy_history_cannot_authorize_plan(self):
        self.setup_history()
        self.client.change = True
        self.assertFalse(
            ops.inspect(self.client, self.root, "documents")["inspection_complete"]
        )
        self.client.change = False
        self.client.reads = 0
        legacy = self.root / "legacy"
        legacy.mkdir()
        self.save(
            legacy / "verification.json",
            {"schema_version": 1, "generation": generation(1)},
        )
        result = ops.inspect(self.client, self.root, "documents")
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["retention"]["review_candidates"], 0)
        with self.assertRaises(ValueError):
            ops.inspect(self.client, self.root, "documents", keep_previous=0)

    def test_reference_identity_is_explicit_and_cannot_conflict(self):
        self.setup_history()
        directory = self.root / "3"
        job = json.loads((directory / "job.json").read_text())
        verification = json.loads((directory / "verification.json").read_text())
        verification["verifier"] = "plain-reference-v1"
        self.save(directory / "verification.json", verification)
        self.assertFalse(
            ops.inspect(self.client, self.root, "documents")["inspection_complete"]
        )
        job["verifier"] = "plain-reference-v1"
        self.save(directory / "job.json", job)
        verification["evidence_sha256"]["job.json"] = ops.digest(directory / "job.json")
        self.save(directory / "verification.json", verification)
        result = ops.inspect(self.client, self.root, "documents")
        self.assertTrue(result["inspection_complete"])
        self.assertIn("reference checker", ops.human(result))

    def test_symlinked_evidence_is_never_followed(self):
        if __import__("os").name != "posix":
            self.skipTest("Symlink test requires POSIX")
        self.setup_history()
        (self.root / "linked").symlink_to(self.root / "3", target_is_directory=True)
        result = ops.inspect(self.client, self.root, "documents")
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["retention"]["review_candidates"], 0)


if __name__ == "__main__":
    unittest.main()
