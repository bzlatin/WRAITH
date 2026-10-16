"""Verify local Codex MCP startup/tool discovery without starting a model turn.

Uses a disposable Codex configuration with no account credentials. The user's
configuration is never read or changed. Raw local evidence may contain paths.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'study'))
from mcp_client import Client, clean_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--codex', default=shutil.which('codex'))
    args = parser.parse_args()
    if os.name != 'posix': raise ValueError('The optional Codex verification controller requires POSIX containment')
    if not args.node or not args.codex: raise ValueError('Install Node.js and Codex first')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    record = dict(schema_version=1, status='incomplete', model_turns_started=0,
                  scope='Codex configuration parsing, MCP startup and tool discovery; not agent adoption')
    client = None
    try:
        with tempfile.TemporaryDirectory(prefix='wraith-codex-check-') as directory:
            config = subprocess.check_output([args.node,str(args.launcher.resolve()),'codex-config',
                '--root',str(args.root.resolve())], env=clean_env(), text=True, timeout=20)
            (Path(directory)/'config.toml').write_text('[analytics]\nenabled = false\n'+config)
            # This variable is the CLI's supported configuration-root setting,
            # confined to this child environment, not a user shell change.
            env = clean_env({'CODEX_HOME':directory})
            record['codex_version'] = subprocess.check_output([args.codex,'--version'],env=env,text=True,stderr=subprocess.PIPE,timeout=15).strip()
            client = Client([args.codex,'app-server'],args.root.resolve(),env)
            client.call('initialize',dict(clientInfo=dict(name='wraith_preview_check',version='0.1.0'),
                        capabilities=dict(experimentalApi=True)),timeout=20)
            client.notify('initialized',{})
            status = client.call('mcpServerStatus/list',dict(limit=10),timeout=30)
            record['server_status'] = status
            server = next(s for s in status['data'] if s['name']=='wraith_context')
            tools = sorted(server['tools'])
            if tools != ['code_context','code_references','code_symbols']: raise ValueError('Unexpected or missing tool catalog')
            record.update(status='passed',tools=tools)
            client.close();client=None
    except BaseException as exc:
        record['error'] = type(exc).__name__+': '+str(exc)
        raise
    finally:
        if client: client.close()
        (output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:record[k] for k in ['status','codex_version','tools','model_turns_started','scope']},indent=2))


if __name__ == '__main__': main()
