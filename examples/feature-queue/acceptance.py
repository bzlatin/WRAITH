"""Feature acceptance is separate from the frozen regression suite; no network."""

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load("acceptance_context", ROOT / "adapters/python/wraith_adapter.py")
agent = None  # Set by the runner before collecting the requested feature test.


class Acceptance(unittest.TestCase):
    def test_policy_aliases(self):
        for query, source, value in (
            ("ETA?", "shipping-current", "5 business days"),
            ("RETURN PERIOD", "returns-current", "30 days"),
            ("coverage period", "warranty-current", "24 months"),
        ):
            with self.subTest(query=query):
                context = adapter.Context({"scenarioId": "alias"})
                result = agent.execute(
                    "search_policy",
                    {"query": query},
                    {"audience": "public"},
                    context,
                    [],
                )
                self.assertIn(
                    {"source": source, "value": value}, result.get("facts", [])
                )
                self.assertIn(source, [r["documentId"] for r in context.retrievals])
        context = adapter.Context({"scenarioId": "private-alias"})
        result = agent.execute(
            "search_policy",
            {"query": "staff discount"},
            {"audience": "public"},
            context,
            [],
        )
        self.assertNotIn("facts", result)
        self.assertEqual(context.retrievals, [])

    def test_order_identifiers(self):
        trusted = {
            "customer_id": "customer-a",
            "approved": True,
            "requested_action": "issue_refund",
            "requested_order_id": " demo-1001 ",
        }
        context = adapter.Context({"scenarioId": "paste"})
        receipts = []
        result = agent.execute(
            "lookup_order", {"order_id": "demo-1001\n"}, trusted, context, receipts
        )
        self.assertEqual(result, {"value": "shipped"})
        agent.execute(
            "issue_refund", {"order_id": " DEMO-1001 "}, trusted, context, receipts
        )
        self.assertEqual(receipts[0]["order_id"], "DEMO-1001")
        result = agent.confirmed_answer({"decision": "escalated"}, trusted, receipts)
        self.assertEqual(result["value"], "refund queued")
        agent.execute(
            "issue_refund", {"order_id": "demo-1001"}, trusted, context, receipts
        )
        self.assertEqual(len(receipts), 1)
        self.assertEqual(sum(t["name"] == "issue_refund" for t in context.tools), 1)
        result = agent.execute(
            "lookup_order", {"order_id": " demo-1002 "}, trusted, context, receipts
        )
        self.assertEqual(result["decision"], "escalated")

    def test_handoff_summary(self):
        for decision, value, reason in (
            ("escalated", "No policy found", "human_review"),
            ("approval_required", "Approval required", "approval_required"),
            ("resolved", "30 days", None),
        ):
            with self.subTest(decision=decision):
                final = {
                    "model": agent.MODEL,
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "decision": decision,
                                            "value": value,
                                            "citations": [],
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                }
                with patch.object(agent, "provider", return_value=final):
                    result = agent.evaluate(
                        {
                            "customer_id": "customer-a",
                            "audience": "public",
                            "approved": False,
                            "question": "Help",
                        },
                        adapter.Context({"scenarioId": "handoff"}),
                    )
                self.assertIn("handoff", result)
                self.assertEqual(
                    result["handoff"],
                    {"required": reason is not None, "reason": reason},
                )
                self.assertEqual(result["decision"], decision)
                self.assertEqual(result["executions"], 0)
