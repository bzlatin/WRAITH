import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import integrated_codex as study


class IntegratedBoundaries(unittest.TestCase):
    def test_only_three_named_tools_get_scoped_permission(self):
        protocol = dict(runtime=dict(model="gpt-6.1-sol", reasoning_effort="medium"))
        with patch.object(study, "MODE", "auto"):
            native = study.command(protocol, Path("/tmp/task"))
            context = study.command(protocol, Path("/tmp/task"), context=True)
        self.assertFalse(any("approval_mode" in x for x in native))
        permissions = [x for x in context if "approval_mode" in x]
        self.assertEqual(permissions, [f'mcp_servers.wraith_context.tools.{t}.approval_mode="auto"' for t in study.TOOLS])
        self.assertIn('approval_policy="never"', context)
        self.assertEqual(context[-1], "-")

    def test_transport_completion_without_real_context_does_not_qualify(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(study, "OUTPUT", Path(folder)):
            sessions = Path(folder) / "sessions"
            sessions.mkdir()
            event = dict(type="item.completed", item=dict(type="mcp_tool_call", server="wraith_context",
                tool="code_context", status="completed", error=None, result={}))
            file = sessions / "probe.events.jsonl"
            for payload, expected in [({}, False), ({"status": "incomplete", "results": [1]}, False),
                                      ({"status": "ok", "results": []}, False),
                                      ({"status": "ok", "results": [{"path": "src/test.ts"}]}, True)]:
                event["item"]["result"] = dict(content=[dict(type="text", text=json.dumps(payload))])
                file.write_text(json.dumps(event) + "\n")
                self.assertEqual(study.verified_payload("probe"), expected)
            event["item"]["result"]["isError"] = True
            file.write_text(json.dumps(event) + "\n")
            self.assertFalse(study.verified_payload("probe"))

    def test_four_setup_failures_leave_exactly_eight_slots(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            study.runner.create_budget(root, "fresh", 12)
            for n in range(4):
                study.runner.reserve(root, "fresh", f"failed-setup-{n}", 12)
            for n in range(8):
                study.runner.reserve(root, "fresh", f"task-{n}", 12)
            with self.assertRaisesRegex(ValueError, "exhausted"):
                study.runner.reserve(root, "fresh", "retry", 12)


if __name__ == "__main__":
    unittest.main()
