"""Conventional integration assertions for the same frozen workflow requirements."""

import asyncio
import json
from pathlib import Path
import sys
import unittest

import adapter

cases = json.loads((Path(__file__).parent / "requirements.json").read_text())
observations = {}


class Context:
    def tool(self, *args, **kwargs):
        pass  # The adapter returns the same observed activity for both runners.


class WeatherCase(unittest.TestCase):
    def __init__(self, case):
        super().__init__("runTest")
        self.case = case

    def id(self):
        return self.case["id"]

    def runTest(self):
        observed = asyncio.run(adapter.evaluate(self.case["input"], Context()))
        observations[self.id()] = observed
        for key, value in self.case["expected"].items():
            self.assertEqual(observed[key], value, f"{self.id()}: {key}")


if __name__ == "__main__":
    suite = unittest.TestSuite(WeatherCase(case) for case in cases)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    Path(sys.argv[1]).write_text(
        json.dumps(
            {
                "failedCases": [t.id() for t, _ in result.failures],
                "executionErrors": [t.id() for t, _ in result.errors],
                "observations": observations,
            },
            indent=2,
        )
        + "\n"
    )
    raise SystemExit(2 if result.errors else 0 if result.wasSuccessful() else 1)
