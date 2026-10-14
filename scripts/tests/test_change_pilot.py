"""Finite queue boundaries and end-to-end replay; never use provider credentials."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location(
    "change_pilot", ROOT / "scripts/change-pilot.py"
)
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)


class ChangeQueueTests(unittest.TestCase):
    def root(self):
        parent = ROOT / ".wraith"
        parent.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="queue-test-", dir=parent)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "campaign"
        binary = ROOT / "target/debug" / queue.EXE
        if not binary.exists():
            self.skipTest("Build the native CLI first")
        queue.prepare(root, binary)
        return root

    def test_feature_queue_replays_all_cases_and_preserves_frozen_tests(self):
        root = self.root()
        initial = queue.art.read(root / "prechange/completion.json")
        self.assertTrue(
            all(not r["passed"] and not r["errors"] for r in initial.values())
        )
        queue.apply_reviewed(root)
        self.assertEqual(queue.run(root, "offline"), 0)
        result = queue.art.read(root / "offline/completion.json")
        self.assertIsNone(result["budget"])
        self.assertEqual(result["overlap"]["bothPassed"], 3)
        self.assertEqual(len(result["results"]), 4)
        for row in result["results"]:
            self.assertEqual(row["components"]["tests"], 10)
            self.assertTrue(row["components"]["passed"])
            self.assertEqual(row["native"]["passed"], 10)
            observations = queue.art.read(
                root / "offline" / (row["variant"] + "-wraith.stdout")
            )["run"]["scenarios"]
            self.assertTrue(
                all(
                    s["run"]["response"]["metadata"]["wraith"]["modelCalls"] == 0
                    for s in observations
                )
            )
        with self.assertRaisesRegex(ValueError, "Attempt already exists"):
            queue.run(root, "offline")
        with self.assertRaisesRegex(ValueError, "separately authorized"):
            queue.run(root, "live")
        queue.verify(root)
        # Fault fixture only: completed evidence tampering must fail closed.
        report = root / "offline/report.md"
        report.write_text("altered evidence")
        with self.assertRaisesRegex(ValueError, "Completed queue evidence changed"):
            queue.verify(root)

    def test_live_budget_and_baseline_stop_without_any_network(self):
        for baseline_passes in (False, True):
            with self.subTest(baseline_passes=baseline_passes):
                root = self.root()
                offline = root / "offline"
                offline.mkdir()
                queue.art.save(
                    offline / "completion.json",
                    {"candidateHashes": queue.candidate_hashes(root)},
                )
                queue.art.save(offline / "seal.json", queue.art.manifest(offline))
                native_commands = []

                def execute(command, directory, label, *args, **kwargs):
                    project = directory / "project"
                    if label == "init":
                        for name in (
                            "wraith.yaml",
                            "wraith.project.json",
                            "wraith_adapter.py",
                        ):
                            (project / name).write_text("trusted")
                    elif (
                        label.endswith("-components")
                        or label.count("-") > 1
                        and not label.endswith("-wraith")
                    ):
                        queue.art.save(
                            Path(command[-1]),
                            {"tests": 10, "passed": True, "failures": [], "errors": []},
                        )
                    elif label.endswith("-wraith"):
                        native_commands.append(command)
                        budget = (
                            project / ".wraith/history/baseline/request-budget.json"
                        )
                        budget.parent.mkdir(parents=True, exist_ok=True)
                        used = queue.art.read(budget)["used"] if budget.exists() else 0
                        queue.art.save(budget, {"limit": 120, "used": used + 30})
                        queue.art.save(
                            project / ".wraith/live-baseline-attempt.json",
                            {"budgetId": "baseline"},
                        )
                        if label == "baseline-wraith":
                            self.assertIn("120", command)
                        else:
                            self.assertNotIn("--max-requests", command)
                        report = project / "report.html"
                        report.write_text("fake report")
                        value = {
                            "run": {
                                "scenarios": [
                                    {
                                        "passed": baseline_passes,
                                        "scenario": {"id": str(i)},
                                        "evaluations": [],
                                    }
                                    for i in range(10)
                                ]
                            },
                            "report": str(report),
                        }
                        queue.art.save(directory / (label + ".stdout"), value)
                        return {"exit": 0 if baseline_passes else 1}
                    else:
                        raise AssertionError(label)
                    return {"exit": 0}

                with patch.object(queue.art, "execute", side_effect=execute):
                    self.assertEqual(
                        queue.run(root, "live", True), 0 if baseline_passes else 1
                    )
                result = queue.art.read(root / "live/completion.json")
                self.assertEqual(len(native_commands), 4 if baseline_passes else 1)
                self.assertEqual(
                    result["budget"],
                    {"limit": 120, "used": 120 if baseline_passes else 30},
                )
                with self.assertRaisesRegex(ValueError, "Attempt already exists"):
                    queue.run(root, "live", True)

    def test_only_agent_file_may_change(self):
        root = self.root()
        path = root / "candidates/policy-aliases/test_override.py"
        path.write_text("not permitted")
        with self.assertRaisesRegex(ValueError, "limited to agent.py"):
            queue.verify(root)
