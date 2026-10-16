import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_compare as study
from mcp_client import clean_env


class CodexBoundaries(unittest.TestCase):
    def test_provider_credentials_are_not_forwarded(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "placeholder", "OPENAI_BASE_URL": "https://example.invalid", "ANTHROPIC_API_KEY": "placeholder"}):
            env = clean_env()
        for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY"):
            self.assertNotIn(key, env)

    def test_attempt_record_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attempted.json"
            study.write_new(path, {"started": True})
            with self.assertRaises(FileExistsError):
                study.write_new(path, {"started": False})
            self.assertEqual(json.loads(path.read_text()), {"started": True})

    def test_catalog_or_failed_call_does_not_count_as_success(self):
        result = study.events_summary([
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "wraith_context", "tool": "code_context", "status": "failed", "error": "failed"}},
            {"type": "turn.failed"},
        ])
        self.assertFalse(result["turn_completed"])
        self.assertTrue(result["turn_failed"])
        self.assertEqual(result["mcp_calls"][0]["status"], "failed")
        self.assertEqual(result["usage"], [])

    def test_usage_and_actual_calls_are_preserved(self):
        usage = {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3}
        result = study.events_summary([
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "wraith_context", "tool": "code_context", "status": "completed", "result": {"isError": False}}},
            {"type": "turn.completed", "usage": usage},
        ])
        self.assertEqual(result["usage"], [usage])
        self.assertEqual(len(result["mcp_calls"]), 1)
        self.assertTrue(result["turn_completed"])


if __name__ == "__main__":
    unittest.main()
