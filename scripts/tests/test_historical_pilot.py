"""Fault checks for pilot evidence and fixed experimental inputs; no network needed."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "historical_pilot", Path(__file__).parents[1] / "historical-pilot.py"
)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class HistoricalEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        binary = root / "wraith"
        binary.write_text("binary fingerprint")
        frozen = root / "frozen"
        frozen.mkdir()
        (frozen / "contracts.json").write_text("[]")
        pilot.save(
            root / "campaign.json",
            {
                "schema": 1,
                "binary": str(binary),
                "binarySha256": pilot.digest(binary),
                "python": sys.executable,
                "installedDependencies": "fixed==1\n",
                "frozen": {"frozen": pilot.manifest(frozen)},
            },
        )

    def test_refuses_changed_policy_and_dependency_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            with patch.object(
                pilot.subprocess, "check_output", return_value="fixed==1\n"
            ):
                pilot.verify(root)
                (root / "frozen/contracts.json").write_text('["relaxed"]')
                with self.assertRaisesRegex(ValueError, "Frozen inputs changed"):
                    pilot.verify(root)
            (root / "frozen/contracts.json").write_text("[]")
            with patch.object(
                pilot.subprocess, "check_output", return_value="fixed==2\n"
            ):
                with self.assertRaisesRegex(
                    ValueError, "Dependency environment changed"
                ):
                    pilot.verify(root)

    def test_completed_evidence_cannot_be_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            folder = root / "historical/buggy"
            folder.mkdir(parents=True)
            result = folder / "result.json"
            result.write_text('{"comparisonExit":1}')
            pilot.save(folder / "evidence.json", pilot.manifest(folder))
            with patch.object(
                pilot.subprocess, "check_output", return_value="fixed==1\n"
            ):
                pilot.verify(root)
                result.write_text('{"comparisonExit":0}')
                with self.assertRaisesRegex(ValueError, "Completed evidence changed"):
                    pilot.verify(root)

    def test_future_campaign_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pilot.save(root / "campaign.json", {"schema": 2})
            with self.assertRaisesRegex(ValueError, "Unsupported campaign schema"):
                pilot.verify(root)


if __name__ == "__main__":
    unittest.main()
