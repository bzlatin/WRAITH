"""Prepare pinned public sources; optional competitor/test dependencies.

All network/installation steps are explicit. Source checkouts are not executed.
Use a new destination for a new study; existing matching clones may be inspected.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from mcp_client import clean_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPO/'.wraith/code-context-study')
    parser.add_argument('--install-serena', action='store_true')
    parser.add_argument('--install-tests', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve(); root.mkdir(parents=True, exist_ok=True)
    output = root/('prepare-'+uuid.uuid4().hex)
    output.mkdir()
    record = dict(schema_version=1, steps=[], status='incomplete')

    def run(command, cwd=None, timeout=180):
        start = time.monotonic()
        result = subprocess.run(command, cwd=cwd, env=clean_env(), capture_output=True, text=True, timeout=timeout)
        record['steps'].append(dict(command=command, seconds=time.monotonic()-start,
                                    exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        (output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        if result.returncode:
            raise RuntimeError('Preparation step failed; inspect saved result.json')
        return result.stdout.strip()

    try:
        protocol = json.loads((HERE/'protocol.json').read_text())
        items = [*protocol['repositories'], dict(name='serena-source', **protocol['serena'])]
        for item in items:
            destination = root/item['name']
            if not destination.exists():
                run(['git','init',str(destination)])
                run(['git','-c','credential.helper=','-C',str(destination),'fetch','--depth=60',item['url'],item['commit']])
                run(['git','-c','core.hooksPath=','-C',str(destination),'checkout','--detach','FETCH_HEAD'])
            actual = run(['git','-C',str(destination),'rev-parse','HEAD'])
            if actual != item['commit']:
                raise ValueError('Existing clone does not match frozen source; preserve it and choose a new root')
            if item['name'] != 'serena-source':
                config = destination/'.serena/project.yml'
                if not config.exists():
                    config.parent.mkdir(exist_ok=True)
                    config.write_text(f'project_name: {item["name"]}\nlanguage_servers:\n- typescript\nencoding: utf-8\n')
        npm = shutil.which('npm')
        if args.install_serena:
            environment = root/'serena-venv'
            if not environment.exists():
                run([sys.executable,'-m','venv',str(environment)])
            python = environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
            run([str(python),'-m','pip','install','--disable-pip-version-check','--cache-dir',str(root/'pip-cache'),str(root/'serena-source')])
            run([npm,'install','--prefix',str(root/'serena-home-ready/language_servers/static/TypeScriptLanguageServer/ts-lsp'),
                 '--cache',str(root/'npm-cache'),'--ignore-scripts','--no-audit','--no-fund','--save-exact',
                 'typescript@5.9.3','typescript-language-server@5.1.3'])
        if args.install_tests:
            for folder in [HERE/'tools', HERE/'tools/zod']:
                run([npm,'ci','--legacy-peer-deps','--ignore-scripts','--no-audit','--no-fund','--cache',str(root/'npm-cache')],cwd=folder)
        record['status'] = 'complete'
    except Exception as exc:
        record['error'] = str(exc)
        raise
    finally:
        (output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Pinned sources ready; no models called. Evidence:', output)


if __name__ == '__main__':
    main()
