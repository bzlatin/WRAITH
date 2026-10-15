"""Protect selection denominators and evidence in the upstream change study."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "upstream_pilot", Path(__file__).parents[1] / "upstream-pilot.py"
)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class UpstreamStudyTests(unittest.TestCase):
    def test_execution_errors_are_not_useful_catches(self):
        for gate, tests in ((2, 0), (130, 0), (1, 2), (0, 5)):
            self.assertEqual(
                pilot.classification(gate, tests), "execution_or_setup_failure"
            )
        self.assertEqual(pilot.classification(3, 0), "inconclusive")
        self.assertEqual(pilot.classification(1, 0), "wraith_failure_needs_review")
        self.assertEqual(pilot.classification(1, 1), "both_checks_fail")
        self.assertEqual(pilot.classification(0, 1), "upstream_failure_only")

    def test_oldest_prs_remain_selected_when_merge_is_stale_or_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = {
                "source": {"revision": "baseline"},
                "selectionRule": {"mode": "open-prs", "limit": 2, "path": "agent.py"},
            }
            pulls = [
                {
                    "number": i,
                    "html_url": f"https://example.test/{i}",
                    "head": {"sha": f"head-{i}"},
                    "created_at": str(i),
                }
                for i in (1, 2, 3)
            ]
            replies = [
                json.dumps(pulls),
                json.dumps([[{"filename": "agent.py"}]]),
                json.dumps([[{"filename": "agent.py"}]]),
            ]
            with (
                patch.object(pilot.subprocess, "check_output", side_effect=replies),
                patch.object(
                    pilot.workflow, "execute", side_effect=[{"exit": 1}, {"exit": 0}]
                ),
                patch.object(pilot, "git", side_effect=["merge-2", "old-base head-2"]),
            ):
                pilot.select_prs(root, state, root)
            queue = pilot.art.read(root / "selection/queue.json")
            self.assertEqual([r["pullRequest"] for r in queue["candidates"]], [1, 2])
            self.assertEqual(
                queue["candidates"][0]["blocked"], "upstream_test_merge_unavailable"
            )
            self.assertEqual(
                queue["candidates"][1]["blocked"], "test_merge_is_stale_or_head_changed"
            )

    def test_mainline_selection_is_chronological_and_not_filtered_by_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = {
                "source": {"revision": "base"},
                "selectionRule": {"mode": "mainline", "limit": 2, "path": "agent.py"},
            }
            replies = [
                "tip",
                "newest\nsecond\nfirst\nbase",
                "base",
                "agent.py",
                "first",
                "agent.py",
            ]
            with (
                patch.object(pilot, "git", side_effect=replies),
                patch.object(pilot.subprocess, "run"),
            ):
                pilot.select(root, state, root, "tip")
            queue = pilot.art.read(root / "selection/queue.json")
            self.assertEqual(
                [r["revision"] for r in queue["candidates"]], ["first", "second"]
            )

    def test_completed_evidence_deletion_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "selection").mkdir()
            pilot.seal(root / "selection")
            (root / "runs").mkdir()
            pilot.art.save(
                root / "state.json",
                {"schema": 1, "frozen": {}, "python": "unused", "packages": []},
            )
            evidence = root / "runs/result.json"
            evidence.write_text("original")
            pilot.art.save(
                root / "completion.json",
                {n: pilot.art.manifest(root / n) for n in ("selection", "runs")},
            )
            with patch.object(
                pilot.workflow.maintained.application, "packages", return_value=[]
            ):
                pilot.verify(root)
                evidence.unlink()
                with self.assertRaisesRegex(ValueError, "disappeared"):
                    pilot.verify(root)

    def test_frozen_suite_cannot_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frozen").mkdir()
            cases = root / "frozen/contracts.json"
            cases.write_text("original cases")
            pilot.art.save(
                root / "state.json",
                {
                    "schema": 1,
                    "frozen": {"frozen": pilot.art.manifest(root / "frozen")},
                },
            )
            cases.write_text("weakened cases")
            with self.assertRaisesRegex(ValueError, "Frozen study"):
                pilot.verify(root)

    def test_incomplete_attempt_is_preserved_and_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "selection").mkdir()
            pilot.art.save(
                root / "selection/queue.json", {"candidates": [{"revision": "abc"}]}
            )
            (root / "runs/abc").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "Incomplete attempt preserved"):
                pilot.run(root, {})

    def test_old_binary_rejected_before_creating_study(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "new-study"
            with patch.object(
                pilot.subprocess,
                "run",
                return_value=type("Probe", (), {"returncode": 2, "stdout": ""})(),
            ):
                with self.assertRaisesRegex(ValueError, "lacks native ci check"):
                    pilot.prepare(root, Path(tmp), Path("old-wraith"), 5)
            self.assertFalse(root.exists())

    def test_baseline_failure_is_not_a_candidate_catch(self):
        self.assertEqual(
            pilot.classification(1, 0, baseline_passed=False), "baseline_failure"
        )

    def test_pinned_queue_rejects_ambiguous_or_invalid_revisions(self):
        pinned = pilot.art.read(pilot.REPO / "docs/evidence/upstream-queue.json")
        pilot.validate_queue(pinned)
        pinned["candidates"][3]["revision"] = "--help"
        with self.assertRaisesRegex(ValueError, "full SHA"):
            pilot.validate_queue(pinned)

    def test_selection_seal_removal_is_detected_before_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "selection").mkdir()
            pilot.art.save(
                root / "state.json",
                {"schema": 1, "frozen": {}, "python": "unused", "packages": []},
            )
            with patch.object(
                pilot.workflow.maintained.application, "packages", return_value=[]
            ):
                with self.assertRaisesRegex(ValueError, "seal missing"):
                    pilot.verify(root)

    def test_completed_study_cannot_run_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "completion.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "Study complete"):
                pilot.run(root, {})


if __name__ == "__main__":
    unittest.main()
