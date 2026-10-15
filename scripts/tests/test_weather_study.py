"""Keep the equal-test comparison and finite study evidence honest."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "weather_study", Path(__file__).parents[1] / "weather-study.py"
)
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


class WeatherStudyTests(unittest.TestCase):
    def test_both_runners_have_identical_frozen_requirements(self):
        requirements = study.art.read(study.FIXTURE / "requirements.json")
        cases = study.art.read(study.FIXTURE / "cases.json")
        self.assertEqual(len(requirements), 10)
        self.assertEqual([r["id"] for r in requirements], [r["id"] for r in cases])
        for requirement, case in zip(requirements, cases):
            self.assertEqual(requirement["input"], case["input"])
            expected = [
                {"path": "/" + key, "check": {"op": "equals", "value": value}}
                for key, value in requirement["expected"].items()
            ]
            self.assertEqual(expected, case["expect"]["json"])

    def fixture(self, root):
        (root / "base").mkdir()
        (root / "base/weather_agent.py").write_text("original")
        (root / "base/wraith.yaml").write_text("trusted policy")
        original = study.art.manifest(root / "base")
        for task in ("retries", "units"):
            folder = root / "candidates" / task
            folder.mkdir(parents=True)
            (folder / "weather_agent.py").write_text("feature")
            (folder / "wraith.yaml").write_text("trusted policy")
        return {"frozen": {"base": original}}

    def test_candidate_cannot_weaken_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.fixture(root)
            study.candidate(root, state, "retries")
            (root / "candidates/retries/wraith.yaml").write_text("weakened")
            with self.assertRaisesRegex(ValueError, "application module"):
                study.candidate(root, state, "retries")

    def test_red_baseline_cannot_create_approved_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            binary = folder / "binary"
            binary.write_text("binary")
            root = folder / "study"
            with (
                patch.object(study, "require_binary"),
                patch.object(
                    study.subprocess,
                    "check_output",
                    side_effect=[study.SOURCE["revision"], b"original"],
                ),
                patch.object(
                    study, "execute", side_effect=[{"exit": n} for n in (0, 1, 0, 1, 1)]
                ),
            ):
                with self.assertRaisesRegex(ValueError, "green baseline"):
                    study.prepare(root, binary, Path("python"), folder)
            self.assertFalse((root / "state.json").exists())
            self.assertFalse((root / "candidates").exists())
            self.assertTrue((root / "setup/phases.json").exists())

    def test_later_failed_attempt_cannot_be_hidden_by_earlier_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self.fixture(root)
            fingerprint = study.candidate(root, state, "retries")[1]
            for i, code in ((1, 0), (2, 1)):
                folder = root / "runs" / f"retries-{i}"
                folder.mkdir(parents=True)
                study.art.save(
                    folder / "result.json",
                    {
                        "source": fingerprint,
                        "completedAt": str(i),
                        "phases": {"wraith": {"exit": code}},
                    },
                )
            with self.assertRaisesRegex(ValueError, "unresolved failures"):
                study.finish(root, state)
            self.assertFalse((root / "completion.json").exists())

    def test_completed_evidence_deletion_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runs").mkdir()
            (root / "candidates").mkdir()
            result = root / "runs/evidence.txt"
            result.write_text("immutable")
            study.art.save(
                root / "state.json",
                {"schema": 1, "frozen": {}, "python": "python", "packages": []},
            )
            study.art.save(
                root / "completion.json",
                {n: study.art.manifest(root / n) for n in ("runs", "candidates")},
            )
            with patch.object(study.subprocess, "check_output", return_value=""):
                study.verify(root)
                result.unlink()
                with self.assertRaisesRegex(ValueError, "disappeared"):
                    study.verify(root)

    def test_reproduction_never_resets_existing_experiments(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(study.subprocess, "run") as execute:
                with self.assertRaisesRegex(ValueError, "Preserve prior"):
                    study.reproduce(Path(tmp), Path("binary"), None, None, True)
                execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
