import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import context_followup as followup
from context_audit import score, validate_citations
from followup_summary import decision


class FollowupBoundaries(unittest.TestCase):
    def budget(self, folder, cap=2):
        p = Path(folder)/'budget.json'
        p.write_text(json.dumps(dict(schema_version=1, experiment=followup.EXPERIMENT,
            model=followup.MODEL, authorized_requests=cap, attempts=[])))
        return p

    def test_fresh_budget_cannot_accept_original_identity_or_refund_failed_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.budget(tmp)
            with patch.dict(os.environ, {'OPENAI_API_KEY':'dummy-not-a-real-key'}), \
                 patch.object(followup.urllib.request, 'build_opener') as opener:
                opener.return_value.open.side_effect = OSError('provider unavailable')
                with self.assertRaisesRegex(RuntimeError, 'provider unavailable'):
                    followup.response([], [], p, 'test', Path(tmp)/'failed.json')
                self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertEqual(followup.reserve(p, 'next', followup.MODEL), 2)
            with self.assertRaisesRegex(ValueError, 'exhausted'):
                followup.reserve(p, 'retry', followup.MODEL)
            data = json.loads(p.read_text()); data['experiment'] = 'code-context-2026-10-16'
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'Wrong experiment'):
                followup.reserve(p, 'old', followup.MODEL)

    def test_page_reads_avoid_end_range_errors_and_return_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); (root/'file.ts').write_text('\n'.join(str(i) for i in range(200)))
            result = json.loads(followup.read_page(root, dict(path='file.ts', start=1, count=160)))
            self.assertEqual(result['end'], 160); self.assertEqual(result['next_start'], 161)
            result = json.loads(followup.read_page(root, dict(path='file.ts', start=190, count=160)))
            self.assertEqual(result['end'], 200); self.assertIsNone(result['next_start'])
            for bad in [0, 161, True]:
                with self.assertRaises(ValueError): followup.read_page(root, dict(path='file.ts', start=1, count=bad))
            tool = next(t for t in followup.basic_tools() if t['name'] == 'read_file')
            self.assertEqual(tool['parameters']['properties']['count']['maximum'], 160)
            self.assertTrue(tool['strict'])

    def test_automatic_context_is_delivered_with_equal_task_and_tools(self):
        task = dict(task='Fix example', approved_edit_paths=['source.ts'], acceptance_test_paths=['source.test.ts'])
        native = followup.initial_inputs(task)
        context = followup.initial_inputs(task, dict(results=[dict(text='untrusted sample')]))
        self.assertEqual(context[:2], native)
        self.assertIn('untrusted', context[2]['content'])
        self.assertFalse(any(t['name'].startswith('code_') for t in followup.basic_tools()))
        self.assertNotIn('fix_commit', str(context))

    def test_file_hit_does_not_count_as_changed_hunk_or_valid_citation(self):
        result = [dict(path='a.ts', start_line=1, end_line=10)]
        scored = score(result, {'a.ts':[dict(start=50, end=55)]})[0]
        self.assertTrue(scored['file_returned']); self.assertEqual(scored['intersected_hunks'], 0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'a.ts').write_text('export const a = 1;')
            with self.assertRaisesRegex(ValueError, 'hash'):
                validate_citations(root, [dict(path='a.ts', source_hash='wrong', start_line=1, end_line=1, text='fabricated')])

    def test_frozen_controller_changes_block_live_before_budget_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'ready.json').write_text(json.dumps(dict(schema_version=1, experiment=followup.EXPERIMENT,
                candidate_sha256={}, boundary_sha256={}, qualification={'task':True})))
            with self.assertRaisesRegex(ValueError, 'changed'):
                followup.live(root, root, 180)
            self.assertFalse((root/'budget.json').exists())

    def test_continuation_requires_joint_success_instead_of_cheap_failed_runs(self):
        rows = [dict(task=str(i), lane=lane, acceptance='passed', list_price_estimate_usd=cost)
                for i in range(3) for lane, cost in [('native','0.10'),('context','0.07')]]
        self.assertTrue(decision(rows, True)['continuation_threshold_met'])
        self.assertFalse(decision(rows, False)['continuation_threshold_met'])
        for r in rows:
            if r['lane'] == 'context' and r['task'] in ['0','1']:
                r.update(acceptance='failed', list_price_estimate_usd='0.001')
        result = decision(rows, True)
        self.assertFalse(result['continuation_threshold_met'])
        self.assertEqual(result['jointly_passed_tasks'], 1)


if __name__ == '__main__': unittest.main()
