"""Challenge validity: a broken harness or missing witness is never a catch."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "challenge", Path(__file__).parents[1] / "coverage-challenge.py"
)
challenge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(challenge)


class CalibrationTests(unittest.TestCase):
    def test_execution_errors_and_unwitnessed_changes_are_excluded(self):
        classify = challenge.classify
        self.assertEqual(classify("seeded_fault", 1, 1, 1, True), "caught")
        self.assertEqual(classify("seeded_fault", 1, 0, 0, True), "missed")
        for phase in (0, 1, 2):
            codes = [1, 1, 1]
            codes[phase] = 2
            self.assertEqual(classify("seeded_fault", *codes, True), "execution_error")
        self.assertEqual(classify("seeded_fault", 0, 1, 1, False), "unvalidated_fault")
        self.assertEqual(classify("seeded_fault", 1, 1, 1, False), "unvalidated_fault")
        self.assertEqual(classify("benign_control", 0, 0, 0, False), "control_pass")
        self.assertEqual(classify("benign_control", 0, 0, 1, False), "control_failure")

    def test_patches_cannot_touch_tests_or_ambiguous_anchors(self):
        source = "def target():\n    return 1\n\ndef other():\n    return 1\n"
        change = {
            "id": "test",
            "file": "llm/models.py",
            "scope": "def target(",
            "old": "return 1",
            "new": "return 2",
        }
        self.assertEqual(
            challenge.mutate(source, change), source.replace("return 1", "return 2", 1)
        )
        with self.assertRaisesRegex(ValueError, "approved application"):
            challenge.mutate(source, dict(change, file="tests/test_tools.py"))
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            challenge.mutate(
                source.replace("    return 1", "    return 1\n    return 1", 1), change
            )
        with self.assertRaises(SyntaxError):
            challenge.mutate(source, dict(change, new="return ("))


if __name__ == "__main__":
    unittest.main()
