import json
import os
import sys
import tempfile
import unittest
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_compare import reserve, source_path
from acceptance import capture


class Boundaries(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'Study process containment requires POSIX')
    def test_timeout_terminates_descendant_with_inherited_output_pipe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            marker = root/'descendant-finished'
            child = 'import time; from pathlib import Path; time.sleep(3); Path(' + repr(str(marker)) + ').write_text("still running")'
            parent = 'import subprocess,time,sys; subprocess.Popen([sys.executable,"-c",' + repr(child) + ']); time.sleep(30)'
            started = time.monotonic()
            result = capture([sys.executable, '-c', parent], root, timeout=0.5)
            self.assertEqual(result['status'], 'execution_error')
            self.assertLess(time.monotonic()-started, 2)
            self.assertFalse(marker.exists())

    def test_attempts_are_reserved_durably_and_failures_cannot_restore_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'budget.json'
            p.write_text(json.dumps(dict(schema_version=1, experiment='code-context-2026-10-16', authorized_requests=2, attempts=[])))
            self.assertEqual(reserve(p, 'baseline', 'test-model'), 1)
            # No completion entry: an interrupted/failed attempt remains consumed.
            self.assertEqual(reserve(p, 'candidate', 'test-model'), 2)
            with self.assertRaisesRegex(ValueError, 'exhausted'):
                reserve(p, 'retry', 'test-model')
            self.assertEqual(len(json.loads(p.read_text())['attempts']), 2)

    def test_foreign_budgets_and_existing_locks_block_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'budget.json'
            p.write_text(json.dumps(dict(schema_version=999, experiment='other', authorized_requests=180, attempts=[])))
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                reserve(p, 'baseline', 'test-model')
            p.with_suffix('.lock').mkdir()
            with self.assertRaises(FileExistsError):
                reserve(p, 'baseline', 'test-model')

    def test_agent_file_access_rejects_escape_symlinks_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'repo'; root.mkdir()
            (root/'safe.ts').write_text('export const safe = 1;')
            (Path(directory)/'outside.ts').write_text('outside')
            (root/'linked.ts').symlink_to(Path(directory)/'outside.ts')
            self.assertEqual(source_path(root, 'safe.ts'), root/'safe.ts')
            for file in ['../outside.ts', 'linked.ts', '.git/config']:
                with self.assertRaises(ValueError):
                    source_path(root, file)


if __name__ == '__main__':
    unittest.main()
