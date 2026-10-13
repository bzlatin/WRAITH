"""Fault tests for fixed evidence, resumability, and incremental workflow coverage."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("trial", ROOT / "scripts/trial.py")
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
BINARY = (
    ROOT
    / "target/debug"
    / ("wraith.exe" if __import__("os").name == "nt" else "wraith")
)


def add_cache(source, key):
    # Controlled fault fixture: preserve actual search instrumentation while varying cache identity.
    source = source.replace(
        "self.searches = 0", "self.searches = 0\n        self.cache = {}"
    )
    begin = source.index("        self.searches += 1")
    end = source.index("        if not documents:", begin)
    block = source[begin:end]
    call = block[block.index("        self.record_tool(") :]
    replacement = (
        f"        key = {key}\n        if key not in self.cache:\n"
        "            self.searches += 1\n            documents = search(query, audience)\n"
        "            self.cache[key] = documents\n"
        + "".join("    " + line + "\n" for line in call.splitlines())
        + "        documents = self.cache[key]\n"
    )
    return source[:begin] + replacement + source[end:]


class TrialTests(unittest.TestCase):
    def test_cache_fault_preserves_failed_evidence_and_repairs_without_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = trial.start(root, BINARY)
            baseline = (root / "baseline/.wraith/runs/baseline.json").read_bytes()
            self.assertEqual(
                [c["result"]["comparisonExit"] for c in state["controls"]], [0, 0, 1]
            )
            controls_before = json.dumps(state["controls"], sort_keys=True)
            self.assertEqual(trial.start(root, BINARY)["id"], state["id"])
            self.assertEqual(
                json.dumps(trial.load(root)["controls"], sort_keys=True),
                controls_before,
            )
            # Claim cache task directly in this isolated fault test; the real queue stays ordered.
            state["tasks"][0]["status"] = "complete"
            trial.save(root / "state.json", state)
            task = trial.next_task(root, state)
            candidate = Path(task["candidate"])
            module = candidate / "support_agent/agent.py"
            original = module.read_text()
            module.write_text(add_cache(original, "query"))
            failed = trial.evaluate(root, state)
            self.assertEqual(failed["unitExit"], 0)
            self.assertEqual(failed["acceptanceExit"], 0)
            self.assertEqual(failed["comparisonExit"], 1)
            self.assertEqual(failed["outcome"], "needs_review")
            self.assertTrue(
                any(c["scenarioId"] == "audience-session" for c in failed["failures"])
            )
            result_path = root / "tasks/retrieval-cache/attempt-001/result.json"
            result_before = result_path.read_bytes()
            self.assertEqual(trial.evaluate(root, state), failed)
            self.assertEqual(len(state["tasks"][1]["attempts"]), 1)
            with self.assertRaises(ValueError):
                trial.finish(root, state)
            triage_file = root / "judgment.json"
            triage_file.write_text(
                json.dumps(
                    dict(
                        classification="actionable_regression",
                        reason="Cache key omits audience",
                        evidence=[
                            "audience-session changes public escalation into staff answer"
                        ],
                    )
                )
            )
            trial.triage(root, state, triage_file)
            self.assertIn(
                "provisional", (result_path.parent / "triage.json").read_text()
            )
            with self.assertRaises(ValueError):
                trial.triage(root, state, triage_file)
            module.write_text(add_cache(original, "(query, audience)"))
            fixed = trial.evaluate(root, state)
            self.assertEqual(fixed["outcome"], "no_observed_regression")
            # Reverting to a previously evaluated source reuses its own selected result,
            # rather than taking the last chronological (possibly failing) attempt.
            module.write_text(add_cache(original, "query"))
            self.assertEqual(trial.evaluate(root, state)["comparisonExit"], 1)
            with self.assertRaises(ValueError):
                trial.finish(root, state)
            module.write_text(add_cache(original, "(query, audience)"))
            self.assertEqual(trial.evaluate(root, state)["comparisonExit"], 0)
            trial.finish(root, state)
            self.assertEqual(result_path.read_bytes(), result_before)
            self.assertEqual(
                (root / "baseline/.wraith/runs/baseline.json").read_bytes(), baseline
            )
            self.assertEqual(state["tasks"][1]["status"], "complete")
            # Completed attempt contents also reject silent edits.
            attempt_file = root / "tasks/retrieval-cache/attempt-002/comparison.stdout"
            before = attempt_file.read_bytes()
            attempt_file.write_text("{}")
            with self.assertRaisesRegex(ValueError, "attempt evidence"):
                trial.load(root)
            attempt_file.write_bytes(before)
            # Existing accepted evidence cannot be changed silently.
            path = root / "baseline/wraith.json"
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "Baseline"):
                trial.load(root)

    def test_lock_and_contract_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with trial.lock(root):
                with self.assertRaisesRegex(ValueError, "locked"):
                    with trial.lock(root):
                        pass
            self.assertFalse((root / "trial.lock").exists())
            frozen = root / "frozen/app"
            frozen.mkdir(parents=True)
            (frozen / "contracts.json").write_text("{}")
            candidate = root / "candidate"
            trial.copy_app(frozen, candidate)
            (candidate / "contracts.json").write_text('{"changed": true}')
            with self.assertRaisesRegex(ValueError, "frozen"):
                trial.validate_candidate(root, candidate)

    def test_interruption_retains_attempt_and_allows_new_evaluation(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # Exercise the real attempt journal without paying for another calibration run.
            app = root / "frozen/app"
            app.mkdir(parents=True)
            (app / "support_agent").mkdir()
            (app / "support_agent/agent.py").write_text("x=1\n")
            state = {"tasks": [{"id": "task", "status": "in_progress", "attempts": []}]}
            candidate = root / "tasks/task/candidate"
            trial.copy_app(app, candidate)
            with patch.object(trial, "evaluate_copy", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    trial.evaluate(root, state)
            attempt = root / "tasks/task/attempt-001"
            self.assertEqual(
                trial.read(attempt / "attempt.json")["status"], "interrupted"
            )
            self.assertFalse((attempt / "result.json").exists())
            # The second attempt receives a distinct directory, preserving the interrupted one.
            with patch.object(trial, "evaluate_copy", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    trial.evaluate(root, state)
            self.assertEqual(len(state["tasks"][0]["attempts"]), 2)


if __name__ == "__main__":
    unittest.main()
