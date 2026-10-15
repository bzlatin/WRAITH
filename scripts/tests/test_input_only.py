"""Explicit input-only calls preserve arity and do not retry application errors."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[2]


class InputOnlyTests(unittest.TestCase):
    def test_python_arity_async_and_body_errors(self):
        adapter = ROOT / "adapters/python/wraith_adapter.py"
        request = json.dumps(
            {"protocolVersion": 1, "scenarioId": "arity", "input": False}
        )
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "agent.py"
            agent.write_text(
                "async def evaluate(input, context=None):\n    return {'value': input, 'context': context is not None}\n"
            )
            for flags, expected in (([], True), (["--input-only"], False)):
                result = subprocess.run(
                    [sys.executable, str(adapter), str(agent) + ":evaluate", *flags],
                    input=request,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                response = json.loads(result.stdout)
                self.assertEqual(
                    response["output"], {"value": False, "context": expected}
                )
                self.assertEqual(response["toolCalls"], [])
            marker = Path(tmp) / "calls.txt"
            agent.write_text(
                "from pathlib import Path\ndef evaluate(input):\n    with Path(__file__).with_name('calls.txt').open('a') as stream: stream.write('x')\n    raise TypeError('application error')\n"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(adapter),
                    str(agent) + ":evaluate",
                    "--input-only",
                ],
                input=request,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("application error", result.stderr)
            self.assertEqual(marker.read_text(), "x")
            result = subprocess.run(
                [sys.executable, str(adapter), str(agent) + ":evaluate", "--typo"],
                input=request,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(marker.read_text(), "x")

    def test_node_arity_and_unknown_flags(self):
        node = os.environ.get("WRAITH_DEMO_NODE") or shutil.which("node")
        if not node:
            self.skipTest("Node not available")
        adapter = ROOT / "adapters/typescript/wraith-adapter.mjs"
        request = json.dumps(
            {"protocolVersion": 1, "scenarioId": "arity", "input": False}
        )
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "agent.mjs"
            agent.write_text(
                "export async function evaluate(input) { return {value: input, arity: arguments.length}; }\n"
            )
            for flags, expected in (([], 2), (["--input-only"], 1)):
                result = subprocess.run(
                    [node, str(adapter), str(agent) + ":evaluate", *flags],
                    input=request,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                response = json.loads(result.stdout)
                self.assertEqual(
                    response["output"], {"value": False, "arity": expected}
                )
                self.assertEqual(response["toolCalls"], [])
            result = subprocess.run(
                [node, str(adapter), str(agent) + ":evaluate", "--typo"],
                input=request,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
