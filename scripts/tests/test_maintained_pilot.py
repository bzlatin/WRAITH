"""Protect frozen upstream tests, patch boundaries, and honest completion."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "maintained_pilot", Path(__file__).parents[1] / "maintained-pilot.py"
)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class MaintainedPilotTests(unittest.TestCase):
    def source(self, root):
        base = root / "base"
        (base / "src").mkdir(parents=True)
        (base / "src/agent.py").write_text("old application")
        (base / "test.py").write_text("unchanged upstream test")
        task = {"id": "fix", "files": ["src/agent.py"]}
        candidate = pilot.candidate(root, task)
        return task, candidate, {"frozen": {"base": pilot.artifacts.manifest(base)}}

    def test_candidate_can_change_application_but_not_upstream_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task, candidate, state = self.source(root)
            (candidate / "src/agent.py").write_text("fixed application")
            pilot.validate_candidate(root, state, task)
            (candidate / "test.py").write_text("weakened test")
            with self.assertRaisesRegex(ValueError, "approved"):
                pilot.validate_candidate(root, state, task)
            (candidate / "test.py").unlink()
            with self.assertRaisesRegex(ValueError, "approved"):
                pilot.validate_candidate(root, state, task)

    def test_reviewed_patch_cannot_write_outside_approved_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changes = root / "frozen/changes"
            changes.mkdir(parents=True)
            (changes / "fix.patch").write_text(
                "--- a/../../escape.py\n+++ b/../../escape.py\n@@ -1 +1 @@\n-old\n+new\n"
            )
            with self.assertRaisesRegex(ValueError, "unapproved"):
                pilot.apply_reviewed(root, {"id": "fix", "files": ["src/agent.py"]})
            self.assertFalse((root / "tasks").exists())

    def test_completion_rejects_deleted_task_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = root / "tasks"
            tasks.mkdir()
            result = tasks / "preserved-result.json"
            result.write_text("completed result")
            pilot.artifacts.save(
                root / "completion.json",
                {"taskEvidence": pilot.artifacts.manifest(tasks)},
            )
            with patch.object(pilot.application, "verify", return_value={}):
                pilot.verify(root)
                result.unlink()
                with self.assertRaisesRegex(ValueError, "disappeared"):
                    pilot.verify(root)

    def test_original_test_control_evidence_cannot_be_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = root / "control.xml"
            result.write_text("original failures")
            state = {"setupEvidence": {"control.xml": pilot.artifacts.digest(result)}}
            with patch.object(pilot.application, "verify", return_value=state):
                pilot.verify(root)
                result.write_text("rewritten as passing")
                with self.assertRaisesRegex(ValueError, "control evidence changed"):
                    pilot.verify(root)

    def test_passing_comparison_with_failed_contract_is_not_a_complete_combined_fix(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frozen = root / "frozen"
            frozen.mkdir()
            pilot.artifacts.save(
                frozen / "tasks.json", [{"id": "combined", "files": []}]
            )
            attempt = root / "tasks/combined/attempt-1"
            attempt.mkdir(parents=True)
            pilot.artifacts.save(
                attempt / "result.json",
                {
                    "source": {},
                    "completedAt": "2026-10-14",
                    "phases": {
                        name: {"exit": 0}
                        for name in (
                            "upstream",
                            "acceptance",
                            "check",
                            "optimized",
                            "strictWarnings",
                        )
                    },
                    "wraith": {
                        "comparison": {"executionErrors": []},
                        "run": {"scenarios": [{"passed": False}]},
                    },
                },
            )
            with patch.object(pilot, "validate_candidate", return_value=(root, {})):
                with self.assertRaisesRegex(ValueError, "retains failed expectations"):
                    pilot.finish(root, {})
            self.assertFalse((root / "completion.json").exists())

    def test_guard_blocks_connections_without_provider_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guard = pilot.FIXTURE / "offline"
            import subprocess
            import sys

            env = pilot.environment(root, root / "source")
            env["PYTHONPATH"] = str(guard)
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import socket; socket.create_connection(('example.invalid',443))",
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbids network", result.stderr)
            self.assertEqual(env["OPENAI_API_KEY"], "offline-fixture")


if __name__ == "__main__":
    unittest.main()
