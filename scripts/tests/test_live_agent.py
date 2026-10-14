"""Offline live-adapter checks: actual attempts reserve budget and fail closed."""

import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

ROOT = Path(__file__).parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = load("live_agent", ROOT / "examples/live-agent/agent.py")
adapter = load("live_context", ROOT / "adapters/python/wraith_adapter.py")


class LiveAgentTests(unittest.TestCase):
    def test_failed_http_attempt_consumes_budget_and_stops_following_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = Path(tmp) / "budget.json"
            budget.write_text('{"limit":40,"used":0}')
            context = adapter.Context({"scenarioId": "failure"})
            opener = MagicMock()
            opener.open.side_effect = urllib.error.HTTPError(
                agent.ENDPOINT, 401, "Unauthorized", {}, io.BytesIO(b"{}")
            )
            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENAI_API_KEY": "test-key",
                        "WRAITH_REQUEST_BUDGET": str(budget),
                    },
                ),
                patch.object(agent.urllib.request, "build_opener", return_value=opener),
            ):
                with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
                    agent.provider({"store": False}, context)
                self.assertEqual(json.loads(budget.read_text())["used"], 1)
                with self.assertRaisesRegex(RuntimeError, "previously failed"):
                    agent.provider({"store": False}, context)
                self.assertEqual(json.loads(budget.read_text())["used"], 1)
                self.assertEqual(opener.open.call_count, 1)

    def test_no_budget_never_opens_a_network_connection(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch.object(agent.urllib.request, "build_opener") as opener,
        ):
            with self.assertRaisesRegex(RuntimeError, "shared request budget"):
                agent.provider({}, adapter.Context({"scenarioId": "offline"}))
            opener.assert_not_called()

    def test_tools_preserve_tenant_approval_and_source_boundaries(self):
        context = adapter.Context({"scenarioId": "boundaries"})
        trusted = {"customer_id": "customer-a", "approved": False, "audience": "public"}
        receipts = []
        result = agent.execute(
            "search_policy",
            {"query": "internal employee discount"},
            trusted,
            context,
            receipts,
        )
        self.assertEqual(result["decision"], "escalated")
        self.assertEqual(context.retrievals, [])
        result = agent.execute(
            "lookup_order", {"order_id": "DEMO-1002"}, trusted, context, receipts
        )
        self.assertEqual(result["decision"], "escalated")
        result = agent.execute(
            "issue_refund", {"order_id": "DEMO-1001"}, trusted, context, receipts
        )
        self.assertEqual(result["decision"], "approval_required")
        self.assertEqual(receipts, [])
        self.assertNotIn("issue_refund", [t["name"] for t in context.tools])
        result = agent.execute(
            "issue_refund",
            {"order_id": "DEMO-1001"},
            dict(trusted, approved=True),
            context,
            receipts,
        )
        self.assertEqual(result["value"], "refund queued")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(context.tools[-1]["name"], "issue_refund")

    def test_two_provider_attempts_pass_real_tool_output_to_final_answer(self):
        context = adapter.Context({"scenarioId": "routing"})
        calls = []

        def provider(payload, context):
            calls.append(payload)
            self.assertFalse(payload["store"])
            if len(calls) == 1:
                return {
                    "model": agent.MODEL,
                    "output": [
                        {
                            "type": "function_call",
                            "name": "search_policy",
                            "arguments": '{"query":"return window"}',
                            "call_id": "fixture_call",
                        }
                    ],
                }
            output = json.loads(payload["input"][-1]["output"])
            self.assertEqual(
                output["facts"], [{"source": "returns-current", "value": "30 days"}]
            )
            return {
                "model": agent.MODEL,
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"decision":"resolved","value":"30 days","citations":["returns-current"]}',
                            }
                        ],
                    }
                ],
            }

        with patch.object(agent, "provider", provider):
            result = agent.evaluate(
                {
                    "customer_id": "customer-a",
                    "approved": False,
                    "audience": "public",
                    "question": "return window",
                },
                context,
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["value"], "30 days")
        self.assertEqual(context.tools[0]["name"], "search_policy")
        self.assertEqual(context.retrievals[0]["documentId"], "returns-current")


if __name__ == "__main__":
    unittest.main()
