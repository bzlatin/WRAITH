"""Workflow evidence must not hide altered tests or a later failed candidate."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "workflow_pilot", Path(__file__).parents[1] / "workflow-pilot.py"
)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class WorkflowEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        (root / "frozen").mkdir()
        pilot.art.save(root / "frozen/task.json", {"files": ["agent.py"]})
        (root / "candidate").mkdir()
        (root / "candidate/agent.py").write_text("feature")
        (root / "candidate/test.py").write_text("frozen test")
        return {"frozen": {"base": pilot.art.manifest(root / "candidate")}}

    def test_existing_tests_and_other_files_cannot_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.fixture(root)
            (root / "candidate/agent.py").write_text("implementation")
            pilot.validate_candidate(root, state)
            (root / "candidate/test.py").write_text("weakened test")
            with self.assertRaisesRegex(ValueError, "returned candidate"):
                pilot.validate_candidate(root, state)

    def test_patch_cannot_change_policy_or_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patchfile = root / "bad.patch"
            patchfile.write_text(
                "--- a/wraith.yaml\n+++ b/wraith.yaml\n@@ -1 +1 @@\n-old\n+weak\n"
            )
            with patch.object(pilot.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "approved"):
                    pilot.apply_patch(root, patchfile)
                run.assert_not_called()

    def test_completed_evidence_deletion_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runs").mkdir()
            result = root / "runs/result.json"
            result.write_text("evidence")
            pilot.art.save(
                root / "state.json",
                {"schema": 1, "frozen": {}, "python": "unused", "packages": []},
            )
            pilot.art.save(
                root / "completion.json", {"runs": pilot.art.manifest(root / "runs")}
            )
            with patch.object(
                pilot.maintained.application, "packages", return_value=[]
            ):
                pilot.verify(root)
                result.unlink()
                with self.assertRaisesRegex(ValueError, "disappeared"):
                    pilot.verify(root)

    def test_latest_failed_feature_cannot_be_hidden_by_prior_passing_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.fixture(root)
            fingerprint = pilot.validate_candidate(root, state)
            for name, data in [
                ("workflow-1", {"source": fingerprint, "completedAt": "2026-10-14"}),
                (
                    "feature-1",
                    {
                        "source": fingerprint,
                        "completedAt": "2026-10-14",
                        "phases": {
                            "acceptance": {"exit": 0},
                            "comparison": {"exit": 1},
                        },
                    },
                ),
            ]:
                folder = root / "runs" / name
                folder.mkdir(parents=True)
                pilot.art.save(folder / "result.json", data)
            with self.assertRaisesRegex(ValueError, "unresolved"):
                pilot.finish(root, state)
            self.assertFalse((root / "completion.json").exists())

    def test_candidate_changed_after_benchmark_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.fixture(root)
            fingerprint = pilot.validate_candidate(root, state)
            for name in ("workflow-1", "feature-1"):
                folder = root / "runs" / name
                folder.mkdir(parents=True)
                pilot.art.save(
                    folder / "result.json",
                    {"source": fingerprint, "completedAt": "2026-10-14"},
                )
            (root / "candidate/agent.py").write_text("later change")
            with self.assertRaisesRegex(ValueError, "after its evaluated"):
                pilot.finish(root, state)


if __name__ == "__main__":
    unittest.main()
