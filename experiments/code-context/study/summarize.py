"""Export a small public summary without machine paths, source snippets or accounts."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main():
    root = REPO/'.wraith/code-context-study'
    live = root/'live-comparison'
    assert (live/'complete.json').exists(), 'Live experiment is incomplete'
    raw = json.loads((live/'summary.json').read_text())
    manifest = json.loads((live/'manifest.json').read_text())
    for relative, digest in manifest['candidate_sha256'].items():
        assert hashlib.sha256((HERE.parent/relative).read_bytes()).hexdigest() == digest, 'Candidate changed after the frozen comparison'
    rates = json.loads((HERE/'pricing-2026-10-16.json').read_text())
    price = {k:Decimal(v) for k,v in rates['usd_per_million_tokens'].items()}
    rows = []
    for row in raw['results']:
        if 'label' not in row:
            rows.append(row);continue
        accepted = json.loads((live/row['label']/'final-acceptance.json').read_text())
        usage = row['usage']
        input_tokens = sum(u.get('input_tokens',0) for u in usage)
        cached_tokens = sum(u.get('input_tokens_details',{}).get('cached_tokens',0) for u in usage)
        output_tokens = sum(u.get('output_tokens',0) for u in usage)
        assert 0 <= cached_tokens <= input_tokens
        estimate = ((input_tokens-cached_tokens)*price['uncached_input'] + cached_tokens*price['cached_input'] + output_tokens*price['output'])/Decimal(1000000)
        rows.append(dict(task=row['task'],lane=row['lane'],status=row['status'],acceptance=row.get('acceptance'),
                         requests_attempted=row['requests_attempted'],requests_completed=row['requests'],
                         task_loop_seconds=round(row['task_seconds'],3),
                         task_and_final_check_seconds=round(row['task_seconds']+accepted['seconds'],3),
                         mcp_startup_seconds=round(row['setup_seconds'],3),input_tokens=input_tokens,cached_input_tokens=cached_tokens,
                         output_tokens=output_tokens,list_price_estimate_usd=str(estimate.quantize(Decimal('.000001')))))
    result=dict(schema_version=1,experiment='code-context-2026-10-16',platform_tested='macOS arm64; Node.js 22.19.0; Python 3.13.0',
                model=manifest['model'],requests_reserved=raw['requests_reserved'],authorized_cap=180,
                protocol_sha256=hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
                tasks_sha256=hashlib.sha256((HERE/'agent-tasks.json').read_bytes()).hexdigest(),
                candidate_sha256=manifest['candidate_sha256'],results=rows,pricing=rates,
                decision='Stop commercial expansion: no demonstrated material task-completion advantage over the free baselines.',
                limitations=['Three source-guided historical fixes; one model observation per lane/task.',
                             'Fifteen model requests per run; unfinished tasks remain failures in this bounded comparison.',
                             'Selected unchanged upstream acceptance files under explicit external configuration, not full repository CI or type checking.',
                             'Different tool interfaces/schemas; comparison measures the complete configured tool choice, not isolated retrieval algorithms.',
                             'Task loop plus final-check timing excludes MCP startup; this is machine time, not human effort.',
                             'List-price estimates use observed usage and current published rates; no actual bill reconciled.',
                             'No independent repeat users, paid demand, Sourcebot or Augment benchmark; process-tree RSS unavailable.'])
    controls = root/'worktree-controls/summary.json'
    if controls.exists(): result['worktree_controls']=json.loads(controls.read_text())
    destination = HERE/'results.json'
    if destination.exists():raise ValueError('Public result already exists; preserve it')
    destination.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(results=rows,requests_reserved=result['requests_reserved'],decision=result['decision']),indent=2))


if __name__=='__main__':
    main()
