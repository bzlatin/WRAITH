"""Run frozen component or feature tests against one chosen application module."""

import argparse
import json
from pathlib import Path
import sys
import time
import unittest
import urllib.request

from acceptance import Acceptance, load
import acceptance

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "kind",
        choices=[
            "components",
            "policy-aliases",
            "order-identifiers",
            "handoff-summary",
        ],
    )
    parser.add_argument("agent", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()

    # Unexpected HTTP in these tests is a failure, never a provider request.
    def blocked(*args, **kwargs):
        raise RuntimeError("Application tests cannot access providers")

    urllib.request.OpenerDirector.open = blocked
    target = load("selected_agent", args.agent)
    if args.kind == "components":
        tests = load(
            "frozen_application_tests", ROOT / "scripts/tests/test_live_agent.py"
        )
        tests.agent = target
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.LiveAgentTests)
    else:
        acceptance.agent = target
        suite = unittest.TestSuite([Acceptance("test_" + args.kind.replace("-", "_"))])
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    args.result.write_text(
        json.dumps(
            {
                "tests": result.testsRun,
                "passed": result.wasSuccessful(),
                "failures": [t.id() for t, _ in result.failures],
                "errors": [t.id() for t, _ in result.errors],
                "machineSeconds": time.monotonic() - started,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
