"""Offline diagnosis. Historical diff ranges score results; they never enter queries."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from mcp_client import clean_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def witness_ranges(repository, task, file, *, tests=False):
    diff = subprocess.check_output(['git', '-C', str(repository), 'diff', '--unified=0',
        task['base_commit'], task['fix_commit'], '--', file], text=True, env=clean_env())
    ranges = []
    for line in diff.splitlines():
        match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
        if match:
            start, count = (match[3], match[4]) if tests else (match[1], match[2])
            start, count = max(1, int(start)), int(count) if count is not None else 1
            # An insertion has no old lines: the adjacent old line is an explicit proxy.
            ranges.append(dict(start=start, end=start + max(1, count) - 1, insertion_proxy=count == 0))
    return ranges


def score(results, witnesses):
    rows = []
    for file, ranges in witnesses.items():
        hits = [r for r in results if r['path'] == file]
        covered = [any(r['start_line'] <= w['end'] and r['end_line'] >= w['start'] for r in hits) for w in ranges]
        rows.append(dict(path=file, file_returned=bool(hits), witness_hunks=len(ranges),
                         intersected_hunks=sum(covered), all_hunks_intersected=bool(ranges) and all(covered),
                         ranges=ranges, intersections=covered))
    return rows


def validate_citations(folder, results):
    for r in results:
        p = folder / r['path']
        if not p.resolve().is_relative_to(folder.resolve()) or p.is_symlink():
            raise ValueError('Citation escapes its checkout')
        raw = p.read_bytes()
        if hashlib.sha256(raw).hexdigest() != r['source_hash']:
            raise ValueError('Citation source hash does not match')
        lines = raw.decode().split('\n')
        if '\n'.join(lines[r['start_line']-1:r['end_line']]) != r['text']:
            raise ValueError('Citation text/range does not match source')


def retrieval(tasks_path, engine, root, worktrees, output):
    output.mkdir(exist_ok=False, parents=True)
    tasks = json.loads(tasks_path.read_text())['tasks']
    rows = []
    for task in tasks:
        folder = worktrees / (task['repository'] + '-base')
        query = task['task']  # Never add approved paths, diff, witness ranges or the fix.
        command = [os.environ.get('WRAITH_STUDY_NODE', shutil.which('node')), str(engine),
                   'context', query, '--root', str(folder), '--cache', str(output/'cache'),
                   '--max-bytes', '16000', '--limit', '8']
        env = clean_env({'NODE_PATH': str(HERE.parent/'node_modules')})
        run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
        raw = dict(exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr)
        (output/(task['id']+'.json')).write_text(json.dumps(raw, indent=2)+'\n')
        row = dict(task=task['id'], status='execution_error', query=query)
        if run.returncode == 0:
            result = json.loads(run.stdout)
            validate_citations(folder, result['results'])
            production = {p:witness_ranges(root/task['repository'], task, p) for p in task['approved_edit_paths']}
            tests = {p:witness_ranges(root/task['repository'], task, p, tests=True) for p in task['acceptance_test_paths']}
            row.update(status='complete', citations_valid=True, snippet_bytes=result['snippet_bytes'],
                       production=score(result['results'], production), tests=score(result['results'], tests),
                       results=[{k:r[k] for k in ['path','name','start_line','end_line']} for r in result['results']])
        rows.append(row)
    summary = dict(schema_version=1, scope='Historical hunk intersection proxies; not complete relevance, correctness, adoption or paid demand',
                   tasks_sha256=hashlib.sha256(tasks_path.read_bytes()).hexdigest(), rows=rows)
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def trace_audit(source):
    rows = []
    for file in sorted(source.glob('*/result.json')):
        d = json.loads(file.read_text())
        calls = d['tool_calls']
        names = [c['name'] for c in calls]
        rows.append(dict(task=d['task'], lane=d['lane'], status=d['status'], acceptance=d.get('acceptance'),
            tool_calls=len(calls), tool_errors=sum('error' in c for c in calls),
            context_calls=names.count('code_context'), symbol_calls=names.count('code_symbols'),
            reference_calls=names.count('code_references'), edited='apply_edit' in names,
            source_result_sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    return dict(schema_version=1, scope='Observed optional tool adoption in the original completed experiment', rows=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    trace = sub.add_parser('traces'); trace.add_argument('--source', type=Path, required=True); trace.add_argument('--output', type=Path, required=True)
    r = sub.add_parser('retrieval')
    for arg in ['tasks', 'engine', 'root', 'worktrees', 'output']:
        r.add_argument('--'+arg, type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'traces':
        if args.output.exists(): raise ValueError('Preserve existing evidence')
        summary = trace_audit(args.source)
        args.output.write_text(json.dumps(summary, indent=2)+'\n')
    else:
        summary = retrieval(args.tasks.resolve(), args.engine.resolve(), args.root.resolve(), args.worktrees.resolve(), args.output.resolve())
    print(json.dumps(summary, indent=2))
