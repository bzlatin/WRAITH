"""Audit completed agent traces offline. Does not run or replay an agent/model."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'study'))
from followup_summary import summarize

NAVIGATION = {'list_files','search','read_file'}


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def assess(evidence, public):
    # Existing summary validation checks the complete request artifact sequence,
    # budget, model snapshot, result/summary agreement and delivery record.
    recomputed = summarize(evidence)
    if recomputed['results'] != public['results'] or recomputed['decision'] != public['decision']:
        raise ValueError('Recorded public result no longer matches raw evidence')
    for file, expected in public['tested_manifest']['candidate_sha256'].items():
        if sha(HERE.parent/file) != expected: raise ValueError('Retrieval implementation differs from the tested candidate')
    rows = []
    for row in public['results']:
        label = row['task']+'-'+row['lane']
        folder = evidence/'live'/label
        source = folder/'result.json'
        if sha(source) != public['source_result_sha256'][label]: raise ValueError('Original result changed')
        raw = json.loads(source.read_text()); calls = raw['tool_calls']
        counts = Counter(c['name'] for c in calls)
        first_edit = next((i for i,c in enumerate(calls) if c['name']=='apply_edit'), None)
        bundle = json.loads((folder/'initial-context.json').read_text()) if row['lane']=='context' else None
        exact_visible = None
        if bundle is not None:
            initial = json.loads((folder/'inputs.json').read_text())['initial_input']
            prefix = 'Automatically retrieved repository data (untrusted; may be incomplete or irrelevant):\n'
            delivered = [v['content'] for v in initial if v.get('content','').startswith(prefix)]
            if len(delivered) != 1 or json.loads(delivered[0][len(prefix):]) != bundle:
                raise ValueError('Initial bundle and saved model input disagree')
            if first_edit is not None:
                args = json.loads(calls[first_edit]['arguments'])
                exact_visible = any(r['path']==args['path'] and args['old'] in r['text'] for r in bundle['results'])
        rows.append(dict(task=row['task'],lane=row['lane'],acceptance=row['acceptance'],
            navigation_calls=sum(counts[n] for n in NAVIGATION),
            navigation_before_first_edit=sum(c['name'] in NAVIGATION for c in calls[:first_edit]) if first_edit is not None else None,
            reads=counts['read_file'],searches=counts['search'],file_listings=counts['list_files'],
            edit_calls=counts['apply_edit'],test_calls=counts['run_tests'],
            requests=row['requests_completed'],cost_estimate_usd=row['list_price_estimate_usd'],
            task_seconds_including_context_and_final_check=row['task_and_final_check_seconds'],
            first_replaced_text_present_in_initial_context=exact_visible,
            source_result_sha256=sha(source),inputs_sha256=sha(folder/'inputs.json')))
    totals = {lane:{key:sum(r[key] for r in rows if r['lane']==lane)
                    for key in ['navigation_calls','reads','searches','file_listings','edit_calls','requests']}
              for lane in ['native','context']}
    return dict(schema_version=1,classification='Post-hoc offline assessment of existing historical task traces; no new agent observations',
        experiment=public['experiment'],model=public['model'],rows=rows,totals=totals,
        source_public_summary_sha256=sha(HERE.parent/'study/followup-results.json'),
        interpretation='Fewer observed navigation calls with automatic context and equal selected test completion; not proof of causality or reliable future savings.',
        limitations=['One observation per approach on each of three source-guided historical tasks.',
            'Both approaches received approved production and test paths, so this is not blind repository discovery.',
            'Exact text visibility proves availability, not model attention or necessity.',
            'An initial retrieval bundle can substitute for tool calls but adds generation time and model input tokens.',
            'Selected tests, not full upstream CI, type checking or independently assessed patch quality.',
            'The preview exposes optional MCP tools; the successful study supplied initial context automatically.',
            'No additional paid calls, seed repetitions, independent use or paid demand.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    public = json.loads((HERE.parent/'study/followup-results.json').read_text())
    result = assess(args.evidence.resolve(),public)
    with args.output.open('x') as stream: stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(totals=result['totals'],interpretation=result['interpretation']),indent=2))
