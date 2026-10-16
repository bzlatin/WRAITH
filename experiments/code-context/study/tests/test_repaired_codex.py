import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import repaired_codex as study


class RepairedBoundaries(unittest.TestCase):
    def test_failed_attempts_are_not_refunded_or_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            study.create_budget(root, "new-study", 2)
            self.assertEqual(study.reserve(root, "new-study", "failed", 2), 1)
            with self.assertRaises(FileExistsError):
                study.create_budget(root, "new-study", 2)
            self.assertEqual(study.reserve(root, "new-study", "next", 2), 2)
            with self.assertRaisesRegex(ValueError, "exhausted"):
                study.reserve(root, "new-study", "retry", 2)
            with self.assertRaisesRegex(ValueError, "Wrong"):
                study.reserve(root, "old-study", "reuse", 2)

    def test_setup_or_error_is_not_successful_context_use(self):
        self.assertFalse(study.successful_context({}))
        call = dict(server="wraith_context", tool="code_context", status="completed", error=None, result_is_error=True)
        self.assertFalse(study.successful_context(dict(mcp_calls=[call])))
        call["result_is_error"] = False
        self.assertTrue(study.successful_context(dict(mcp_calls=[call])))

    def test_commands_force_subscription_and_isolate_configuration(self):
        p = dict(runtime=dict(model="gpt-6.1-sol", reasoning_effort="medium"))
        native = study.command(p, Path("/tmp/example"))
        context = study.command(p, Path("/tmp/example"), context=True)
        self.assertIn("--ignore-user-config", native)
        self.assertIn('forced_login_method="chatgpt"', native)
        self.assertFalse(any("mcp_servers" in item for item in native))
        self.assertTrue(any("mcp_servers.wraith_context.args=" in item for item in context))
        diagnostic = study.command(p, Path("/tmp/example"), diagnostic=True)
        self.assertEqual(diagnostic[diagnostic.index("--sandbox") + 1], "read-only")


if __name__ == "__main__":
    unittest.main()
