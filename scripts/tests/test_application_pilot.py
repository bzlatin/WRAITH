"""Pilot boundaries: do not replace baselines or accept altered completed history."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "application_pilot", Path(__file__).parents[1] / "application-pilot.py"
)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class ApplicationEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        binary = root / "wraith"
        binary.write_text("binary")
        frozen = root / "frozen"
        frozen.mkdir()
        (frozen / "contracts.json").write_text("[]")
        project = root / "project"
        (project / ".wraith/history/baseline").mkdir(parents=True)
        pointer = project / ".wraith/baseline.json"
        pointer.write_text('{"id":"baseline"}')
        (project / "wraith.yaml").write_text("trusted policy")
        history = project / ".wraith/history/baseline/run.json"
        history.write_text("baseline evidence")
        state = {
            "schema": 1,
            "binary": str(binary),
            "binarySha256": pilot.artifacts.digest(binary),
            "python": "unused",
            "packages": [],
            "frozen": {"frozen": pilot.artifacts.manifest(frozen)},
            "projectFiles": {
                "wraith.yaml": pilot.artifacts.digest(project / "wraith.yaml")
            },
            "baselinePointerSha256": pilot.artifacts.digest(pointer),
            "baselineHistory": {str(history): pilot.artifacts.digest(history)},
        }
        pilot.artifacts.save(root / "campaign.json", state)
        return project

    def test_changed_baseline_pointer_or_policy_is_rejected(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(pilot, "packages", return_value=[]),
        ):
            root = Path(tmp)
            project = self.fixture(root)
            pilot.verify(root)
            pointer = project / ".wraith/baseline.json"
            pointer.write_text('{"id":"new"}')
            with self.assertRaisesRegex(ValueError, "baseline pointer changed"):
                pilot.verify(root)
            pointer.write_text('{"id":"baseline"}')
            (project / "wraith.yaml").write_text("relaxed policy")
            with self.assertRaisesRegex(ValueError, "Trusted project policy"):
                pilot.verify(root)

    def test_sealed_native_report_cannot_change(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(pilot, "packages", return_value=[]),
        ):
            root = Path(tmp)
            project = self.fixture(root)
            report = project / ".wraith/history/check/report.html"
            report.parent.mkdir()
            report.write_text("original failure")
            pilot.artifacts.save(
                root / "completion.json",
                {
                    "schema": 1,
                    "nativeHistory": pilot.artifacts.manifest(
                        project / ".wraith/history"
                    ),
                },
            )
            pilot.verify(root)
            report.write_text("rewritten pass")
            with self.assertRaisesRegex(ValueError, "Completed native history changed"):
                pilot.verify(root)

    def test_deleted_completed_calibration_is_rejected(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(pilot, "packages", return_value=[]),
        ):
            root = Path(tmp)
            project = self.fixture(root)
            result = root / "changes/fault/result.json"
            result.parent.mkdir(parents=True)
            result.write_text("saved fault evidence")
            pilot.artifacts.save(
                root / "completion.json",
                {
                    "schema": 1,
                    "nativeHistory": pilot.artifacts.manifest(
                        project / ".wraith/history"
                    ),
                    "changeEvidence": pilot.artifacts.manifest(root / "changes"),
                },
            )
            pilot.verify(root)
            result.unlink()
            with self.assertRaisesRegex(
                ValueError, "calibration evidence changed or disappeared"
            ):
                pilot.verify(root)


if __name__ == "__main__":
    unittest.main()
