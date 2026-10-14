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
pilot = load("live_pilot", ROOT / "scripts/live-pilot.py")


def function_call(name, arguments, call_id="call"):
    return {
        "output": [
            {
                "type": "function_call",
                "name": name,
                "arguments": json.dumps(arguments),
                "call_id": call_id,
            }
        ]
    }


def final_answer(value="refund queued", decision="resolved"):
    return {
        "model": agent.MODEL,
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {"decision": decision, "value": value, "citations": []}
                        ),
                    }
                ],
            }
        ],
    }


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

    def test_exhausted_budget_prevents_another_http_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = Path(tmp) / "budget.json"
            budget.write_text('{"limit":2,"used":0}')
            context = adapter.Context({"scenarioId": "cap"})
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value.read.return_value = (
                json.dumps(
                    {
                        "status": "completed",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    }
                ).encode()
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
                agent.provider({}, context)
                agent.provider({}, context)
                with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
                    agent.provider({}, context)
            self.assertEqual(opener.open.call_count, 2)
            self.assertEqual(json.loads(budget.read_text())["used"], 2)

    def test_invalid_provider_response_stops_later_requests_without_retry(self):
        for response in (
            b"invalid JSON",
            b"[]",
            b'{"status":"incomplete","usage":{"input_tokens":1,"output_tokens":1}}',
            b'{"status":"completed","usage":{"input_tokens":true,"output_tokens":1}}',
        ):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as tmp:
                budget = Path(tmp) / "budget.json"
                budget.write_text('{"limit":60,"used":0}')
                context = adapter.Context({"scenarioId": "invalid"})
                opener = MagicMock()
                opener.open.return_value.__enter__.return_value.read.return_value = (
                    response
                )
                with (
                    patch.dict(
                        os.environ,
                        {
                            "OPENAI_API_KEY": "test-key",
                            "WRAITH_REQUEST_BUDGET": str(budget),
                        },
                    ),
                    patch.object(
                        agent.urllib.request, "build_opener", return_value=opener
                    ),
                ):
                    with self.assertRaises(RuntimeError):
                        agent.provider({}, context)
                    with self.assertRaisesRegex(RuntimeError, "previously failed"):
                        agent.provider({}, context)
                self.assertEqual(opener.open.call_count, 1)
                self.assertEqual(json.loads(budget.read_text())["used"], 1)

    def test_tools_preserve_tenant_approval_and_source_boundaries(self):
        context = adapter.Context({"scenarioId": "boundaries"})
        trusted = {
            "customer_id": "customer-a",
            "approved": False,
            "audience": "public",
            "requested_action": "issue_refund",
            "requested_order_id": "DEMO-1001",
        }
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
        agent.execute(
            "lookup_order", {"order_id": "DEMO-1001"}, trusted, context, receipts
        )
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

    def test_lookup_refund_confirmation_uses_three_attempts_and_real_receipt(self):
        context = adapter.Context({"scenarioId": "multi-step"})
        arguments = {"order_id": "DEMO-1001"}
        responses = [
            function_call("lookup_order", arguments, "lookup"),
            function_call("issue_refund", arguments, "refund"),
            final_answer(),
        ]
        with patch.object(agent, "provider", side_effect=responses) as provider:
            result = agent.evaluate(
                {
                    "customer_id": "customer-a",
                    "audience": "public",
                    "approved": True,
                    "requested_action": "issue_refund",
                    "requested_order_id": "DEMO-1001",
                    "question": "Refund it",
                },
                context,
            )
        self.assertEqual(provider.call_count, 3)
        self.assertEqual(
            [t["name"] for t in context.tools], ["lookup_order", "issue_refund"]
        )
        self.assertEqual(result["executions"], 1)
        self.assertEqual(result["receipts"][0]["order_id"], "DEMO-1001")
        self.assertEqual(result["text"], "refund queued")
        sent = provider.call_args_list
        self.assertEqual(
            json.loads(sent[1].args[0]["input"][-1]["output"]), {"value": "shipped"}
        )
        self.assertEqual(
            json.loads(sent[2].args[0]["input"][-1]["output"]),
            {"value": "refund queued"},
        )
        self.assertNotIn("tools", sent[2].args[0])

    def test_refund_authorization_and_idempotency_are_application_enforced(self):
        context = adapter.Context({"scenarioId": "action-boundaries"})
        trusted = {
            "customer_id": "customer-a",
            "audience": "public",
            "approved": True,
            "requested_action": "issue_refund",
            "requested_order_id": "DEMO-1001",
        }
        args = {"order_id": "DEMO-1001"}
        receipts = []
        self.assertIn(
            "error", agent.execute("issue_refund", args, trusted, context, receipts)
        )
        agent.execute("lookup_order", args, trusted, context, receipts)
        for changes in (
            {"requested_action": None},
            {"requested_order_id": "DEMO-1002"},
            {"customer_id": "customer-b"},
            {"approved": "true"},
        ):
            result = agent.execute(
                "issue_refund", args, dict(trusted, **changes), context, receipts
            )
            self.assertIn(result["decision"], ("escalated", "approval_required"))
            self.assertEqual(receipts, [])
        agent.execute("issue_refund", args, trusted, context, receipts)
        repeated = agent.execute("issue_refund", args, trusted, context, receipts)
        self.assertTrue(repeated["receiptReused"])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(sum(t["name"] == "issue_refund" for t in context.tools), 1)

    def test_tool_loops_are_bounded_and_parallel_batches_do_not_execute(self):
        payload = {
            "customer_id": "customer-a",
            "audience": "public",
            "approved": False,
            "question": "Return window?",
        }
        call = function_call("search_policy", {"query": "return"})
        context = adapter.Context({"scenarioId": "loop"})
        with patch.object(
            agent, "provider", side_effect=[call, call, final_answer("30 days")]
        ) as provider:
            result = agent.evaluate(payload, context)
        self.assertEqual(provider.call_count, 3)
        self.assertEqual(len(context.tools), 2)
        self.assertEqual(result["text"], "30 days")
        context = adapter.Context({"scenarioId": "batch"})
        with patch.object(
            agent, "provider", return_value={"output": call["output"] * 2}
        ) as provider:
            with self.assertRaisesRegex(ValueError, "one sequential tool call"):
                agent.evaluate(payload, context)
        self.assertEqual(context.tools, [])
        self.assertEqual(provider.call_count, 1)

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


class LivePilotTests(unittest.TestCase):
    def fixture(self, root):
        (root / "frozen").mkdir()
        (root / "frozen/cases.json").write_text("[]")
        binary = root / "wraith"
        binary.write_text("frozen binary")
        (root / "project/.wraith/history").mkdir(parents=True)
        state = {
            "schema": 2,
            "cap": 60,
            "caseCount": 1,
            "requirePassingBaseline": True,
            "binary": str(binary),
            "binarySha256": pilot.art.digest(binary),
            "frozen": pilot.art.manifest(root / "frozen"),
            "projectFiles": {},
            "phases": {"doctor": {"exit": 0}},
            "plan": "offline test",
        }
        pilot.art.save(root / "state.json", state)

    def test_failed_baseline_stops_before_candidate_and_cannot_be_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)

            def execute(command, cwd, label, *args, **kwargs):
                self.assertEqual(label, "baseline")
                self.assertIn("60", command)
                pilot.art.save(
                    root / "baseline.stdout",
                    {"run": {"scenarios": [{"passed": False, "run": {}}]}},
                )
                return {"exit": 1}

            with (
                patch.object(pilot.art, "execute", side_effect=execute) as execute,
                patch.object(pilot, "budget", return_value={"limit": 60, "used": 3}),
            ):
                self.assertEqual(pilot.run(root, True), 1)
                self.assertEqual(execute.call_count, 1)
                with self.assertRaisesRegex(ValueError, "already attempted"):
                    pilot.run(root, True)
            self.assertNotIn(
                "candidate", pilot.art.read(root / "completion.json")["phases"]
            )
            self.assertIn("Candidate skipped", (root / "report.md").read_text())

    def test_passing_baseline_allows_one_candidate_on_same_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)

            def execute(command, cwd, label, *args, **kwargs):
                if label == "candidate":
                    self.assertNotIn("--max-requests", command)
                pilot.art.save(
                    root / f"{label}.stdout",
                    {"run": {"scenarios": [{"passed": True, "run": {}}]}},
                )
                return {"exit": 0}

            with (
                patch.object(pilot.art, "execute", side_effect=execute) as execute,
                patch.object(pilot, "budget", return_value={"limit": 60, "used": 6}),
            ):
                self.assertEqual(pilot.run(root, True), 0)
                self.assertEqual(execute.call_count, 2)
            self.assertEqual(
                pilot.art.read(root / "completion.json")["budget"]["used"], 6
            )

    def test_empty_successful_baseline_is_rejected_without_rewriting_its_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)

            def execute(command, cwd, label, *args, **kwargs):
                pilot.art.save(root / "baseline.stdout", {"run": {"scenarios": []}})
                return {"exit": 0}

            with (
                patch.object(pilot.art, "execute", side_effect=execute) as execute,
                patch.object(pilot, "budget", return_value={"limit": 60, "used": 0}),
            ):
                self.assertEqual(pilot.run(root, True), 2)
                self.assertEqual(execute.call_count, 1)
            phase = pilot.art.read(root / "completion.json")["phases"]["baseline"]
            self.assertEqual(phase["exit"], 0)
            self.assertIn("validationError", phase)


if __name__ == "__main__":
    unittest.main()
