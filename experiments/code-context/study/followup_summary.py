"""Sanitized, reproducible summary of a completed context-delivery experiment."""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from statistics import median

import context_followup as study


def estimate(usage, rates):
    inputs = sum(u.get('input_tokens', 0) for u in usage)
    cached = sum(u.get('input_tokens_details', {}).get('cached_tokens', 0) for u in usage)
    outputs = sum(u.get('output_tokens', 0) for u in usage)
    if not 0 <= cached <= inputs: raise ValueError('Invalid usage accounting')
    cost = ((inputs-cached)*Decimal(rates['uncached_input']) + cached*Decimal(rates['cached_input'])
            + outputs*Decimal(rates['output']))/Decimal(1000000)
    return dict(input_tokens=inputs, cached_input_tokens=cached, output_tokens=outputs), cost


def decision(rows, complete):
    passed = {lane:sum(r.get('acceptance') == 'passed' for r in rows if r['lane'] == lane) for lane in ['native','context']}
    pairs = []
    for task in sorted({r['task'] for r in rows}):
        pair = {r['lane']:r for r in rows if r['task'] == task}
        if set(pair) == {'native','context'} and all(r.get('acceptance') == 'passed' for r in pair.values()):
            pairs.append(pair)
    reduction = None
    if pairs:
        native = median(Decimal(p['native']['list_price_estimate_usd']) for p in pairs)
        context = median(Decimal(p['context']['list_price_estimate_usd']) for p in pairs)
        if native: reduction = 1-context/native
    qualifies = bool(complete and len(rows) == 6 and passed['context'] >= passed['native']
        and len(pairs) >= 2 and reduction is not None and reduction >= Decimal('0.20'))
    return dict(passed=passed, jointly_passed_tasks=len(pairs),
        median_cost_reduction_on_jointly_passed_pairs=str(reduction) if reduction is not None else None,
        continuation_threshold_met=qualifies,
        next_action='Consider an external repeat-use test; no SaaS or revenue claim' if qualifies else
                    'Stop expansion at the local utility; no automatic reruns, hosted work or feature queue')


def retrieval_metrics(folder):
    data = json.loads((folder/'summary.json').read_text())
    return [dict(task=r['task'], status=r['status'], citations_valid=r.get('citations_valid'),
                 snippet_bytes=r.get('snippet_bytes'), **{k:[{field:p[field] for field in
                     ['path','file_returned','witness_hunks','intersected_hunks','all_hunks_intersected']} for p in r.get(k, [])]
                     for k in ['production','tests']}) for r in data['rows']]


def summarize(output):
    raw = json.loads((output/'live/summary.json').read_text())
    complete = json.loads((output/'live/complete.json').read_text())['complete']
    manifest = json.loads((output/'live/manifest.json').read_text())
    budget = json.loads((output/'budget.json').read_text())
    if budget['experiment'] != study.EXPERIMENT or manifest['experiment'] != study.EXPERIMENT:
        raise ValueError('Wrong experiment')
    if [v['number'] for v in budget['attempts']] != list(range(1, len(budget['attempts'])+1)):
        raise ValueError('Noncontiguous attempt history')
    if len(budget['attempts']) > budget['authorized_requests']: raise ValueError('Budget exceeded')
    pricing = json.loads((study.HERE/'pricing-2026-10-16.json').read_text())
    rows = []; artifact_attempts = []; raw_hashes = {}
    for row in raw['results']:
        if 'label' not in row:
            rows.append(row); continue
        folder = output/'live'/row['label']; path = folder/'result.json'
        if json.loads(path.read_text()) != row: raise ValueError('Summary and case result disagree')
        raw_hashes[row['label']] = hashlib.sha256(path.read_bytes()).hexdigest()
        attempts = []
        for artifact in sorted(folder.glob('request-*.json')):
            request = json.loads(artifact.read_text()); attempts.append(request['attempt'])
            if 'response' in request and request['response'].get('model') != study.MODEL:
                raise ValueError('Unexpected model snapshot')
        expected = [v['number'] for v in budget['attempts'] if v['label'] == row['label']]
        if attempts != expected or len(expected) != row['requests_attempted']: raise ValueError('Request evidence is incomplete')
        artifact_attempts.extend(attempts)
        usage, cost = estimate(row['usage'], pricing['usd_per_million_tokens'])
        accepted = json.loads((folder/'final-acceptance.json').read_text()) if (folder/'final-acceptance.json').exists() else {}
        initial = json.loads((folder/'inputs.json').read_text()) if (folder/'inputs.json').exists() else {}
        bundle_included = any('Automatically retrieved repository data' in item.get('content','') for item in initial.get('initial_input', []))
        if bundle_included != row.get('context_delivered', False): raise ValueError('Context delivery evidence disagrees')
        rows.append(dict(task=row['task'], lane=row['lane'], status=row['status'], acceptance=row.get('acceptance'),
            requests_attempted=row['requests_attempted'], requests_completed=row['requests'], **usage,
            list_price_estimate_usd=str(cost), automatic_context_delivered=bundle_included,
            context_seconds=round(row['context_seconds'], 3),
            task_and_final_check_seconds=round(row.get('task_seconds',0)+accepted.get('seconds',0), 3),
            worktree_setup_seconds=round(row.get('setup_seconds',0), 3),
            tool_errors=sum('error' in c for c in row['tool_calls']), tool_calls=len(row['tool_calls'])))
    if sorted(artifact_attempts) != list(range(1, len(budget['attempts'])+1)): raise ValueError('Missing reserved-attempt artifacts')
    complete = complete and all(manifest['qualification'].values()) and all(r.get('status') in ['model_finished','request_limit'] for r in rows)
    result = dict(schema_version=1, experiment=study.EXPERIMENT, model=study.MODEL,
        tested_platform='macOS arm64; Node.js 22.19.0; Python 3.13.0', complete=complete,
        authorized_cap=budget['authorized_requests'], requests_reserved=len(budget['attempts']),
        results=rows, decision=decision(rows, complete), tested_manifest=manifest, source_result_sha256=raw_hashes,
        pricing=pricing, total_list_price_estimate_usd=str(sum((Decimal(r.get('list_price_estimate_usd','0')) for r in rows), Decimal(0))),
        limitations=['Three source-guided historical fixes, one observation per approach/task; no statistical or causal generalization.',
            'Automatic delivery is the treatment; optional MCP adoption was measured separately in the original experiment.',
            'Both approaches received approved production/test paths and the same tools and 30-request limit.',
            'Context generation is included in machine time; its serialized input is included in provider token usage.',
            'Selected unchanged test files under external configuration; not full CI or type checking.',
            'List-price token estimate, not an invoice; no human-time, independent repeat-use or paid-demand evidence.'])
    for label, name in [('diagnostic_before','old-before'), ('diagnostic_after','old-after-final'),
                        ('fresh_before','fresh-before'), ('fresh_after','fresh-after')]:
        if (output/name/'summary.json').exists(): result[label] = retrieval_metrics(output/name)
    if (output/'original-tool-use.json').exists(): result['original_optional_tool_use'] = json.loads((output/'original-tool-use.json').read_text())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.output.resolve())
    study.write_new(args.public, result)
    print(json.dumps(dict(requests=result['requests_reserved'], results=result['results'], decision=result['decision']), indent=2))
