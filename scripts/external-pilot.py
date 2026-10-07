#!/usr/bin/env python3
"""Clone pinned upstream agents and verify real offline orchestration through Wraith."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / 'examples/external-agents/sources.json').read_text())


def run(args, cwd=ROOT, **kwargs):
    return subprocess.run([str(a) for a in args], cwd=cwd, check=True, **kwargs)


def clone(name, source):
    directory = ROOT / '.wraith/external' / name
    if not directory.exists():
        run(['git', 'clone', '--filter=blob:none', '--no-checkout', source['url'], directory])
        run(['git', 'sparse-checkout', 'init', '--cone'], directory)
        run(['git', 'sparse-checkout', 'set', *source['paths']], directory)
        run(['git', 'fetch', '--depth', '1', 'origin', source['revision']], directory)
        run(['git', 'checkout', '--detach', source['revision']], directory)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=directory, text=True).strip()
    if revision != source['revision']:
        raise ValueError(f'{directory} is at {revision}; refusing to reset an existing checkout')
    example = directory / source['example']
    if not example.is_file():
        run(['git', 'sparse-checkout', 'set', *source['paths']], directory)
    return example


def main(binary, python, install):
    if install:
        environment = ROOT / '.wraith/external-venv'
        if not environment.exists(): run([sys.executable, '-m', 'venv', environment])
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        run([python, '-m', 'pip', 'install', '-r', ROOT / 'examples/external-agents/requirements.txt'])
    records = []
    for name, source in SOURCES.items():
        example = clone(name, source)
        output = ROOT / '.wraith/external-pilot' / name
        output.mkdir(parents=True, exist_ok=True)
        wrapper = ROOT / 'examples/external-agents' / ('pydantic_weather.py' if name == 'pydantic-ai' else 'langgraph_tools.py')
        cases = ([dict(id=city.lower(), input=dict(city=city, temperature=temp), expect=dict(tools_called=['get_lat_lng', 'get_weather'], output_contains=[city, f'{temp} °C', 'Sunny'])) for city, temp in [('London', 24), ('Paris', 18), ('Tokyo', 27)]] if name == 'pydantic-ai' else [dict(id=f'search-{i}', input=dict(text=text), expect=dict(tools_called=['search'], output_contains=['done.'])) for i, text in enumerate(['Search v3', 'Look up v3', 'Research the tools channel'], 1)])
        config = output / 'wraith.json'
        config.write_text(json.dumps(dict(version=1, agent=dict(command=shlex.join([str(python), str(ROOT / 'adapters/python/wraith_adapter.py'), str(wrapper) + ':evaluate']), timeout_ms=30000), tests=cases), indent=2))
        env = dict(os.environ, WRAITH_EXTERNAL_SOURCE=str(example))
        env.pop('WRAITH_EXTERNAL_VARIANT', None)
        def execute(args, expected):
            result = subprocess.run([str(binary), '--config', str(config), *args, '--output', 'json'], env=env, capture_output=True, text=True)
            if result.returncode != expected:
                data = json.loads(result.stdout) if result.stdout else {}
                errors = [s['run']['error'] for s in data.get('run', {}).get('scenarios', []) if s['run'].get('error')]
                raise RuntimeError(f'{name} unexpected exit {result.returncode}: {result.stderr}\n{errors or result.stdout[:2000]}')
            return json.loads(result.stdout)
        execute(['baseline', '--replace'], 0)
        env['WRAITH_EXTERNAL_VARIANT'] = 'skip-tool'
        result = execute(['check'], 1)
        changes = result['comparison']['changes']
        detected = sorted({change['scenarioId'] for change in changes if change['severity'] == 'failure'})
        if detected != sorted(case['id'] for case in cases): raise RuntimeError('Controlled tool regressions were missed')
        records.append(dict(repository=source['url'], revision=source['revision'], baselineCases=len(cases), detectedRegressions=len(detected), modelRequests=0, report=result['report']))
        print(f'PASS {name}: {len(cases)} upstream baseline cases, {len(detected)} controlled regressions detected; zero live model requests.')
    summary = dict(records=records, scope='Real upstream orchestration with hermetic model/tool fixtures. Controlled tool-selection faults; not naturally occurring production regressions or model quality estimates.')
    path = ROOT / '.wraith/external-pilot/summary.json'
    path.write_text(json.dumps(summary, indent=2) + '\n')
    print(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT / 'target/debug' / ('wraith.exe' if os.name == 'nt' else 'wraith'))
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--install', action='store_true', help='Install dependencies in an isolated ignored venv')
    args = parser.parse_args()
    try:
        main(args.binary.resolve(), Path(os.path.abspath(args.python)), args.install)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'{error}\n')
