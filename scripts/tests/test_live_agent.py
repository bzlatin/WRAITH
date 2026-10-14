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
    def test_recorded_false_refund_confirmation_is_suppressed_offline(self):
        observed = json.loads((ROOT / "docs/evidence/live-support.json").read_text())
        record = next(
            c
            for c in observed["versions"]["candidate"]["cases"]
            if c["id"] == "refund-approved"
        )
        self.assertEqual(record["executedTools"], ["lookup_order"])
        self.assertEqual(record["output"]["executions"], 0)
        draft = {
            key: record["output"][key] for key in ("decision", "value", "citations")
        }
        payload = {
            "approved": True,
            "requested_action": "issue_refund",
            "requested_order_id": "DEMO-1001",
        }
        answer = agent.confirmed_answer(draft, payload, [])
        self.assertEqual(answer["decision"], "escalated")
        self.assertEqual(answer["value"], "refund not executed; contact support")
        answer = agent.confirmed_answer(draft, payload, [{"order_id": "DEMO-1002"}])
        self.assertEqual(answer["decision"], "escalated")
        answer = agent.confirmed_answer(draft, payload, [{"order_id": "DEMO-1001"}])
        self.assertEqual(answer["value"], "refund queued")
        denied = agent.confirmed_answer(draft, dict(payload, approved=False), [])
        self.assertEqual(denied["decision"], "approval_required")
        context = adapter.Context({"scenarioId": "observed-refund"})
        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "lookup_order",
                        "arguments": '{"order_id":"DEMO-1001"}',
                        "call_id": "lookup",
                    }
                ]
            },
            {
                "model": agent.MODEL,
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(draft)}],
                    }
                ],
            },
        ]
        with patch.object(agent, "provider", side_effect=responses) as provider:
            result = agent.evaluate(
                dict(
                    payload,
                    customer_id="customer-a",
                    audience="public",
                    question="Refund my order",
                ),
                context,
            )
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["text"], "refund not executed; contact support")
        self.assertEqual(result["modelDraft"], draft)
        self.assertEqual(result["executions"], 0)
        self.assertEqual([tool["name"] for tool in context.tools], ["lookup_order"])

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
