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
    parser.add_argument('--allow-read-tools', action='store_true', help='Generate explicit per-tool automatic approval for the three local read tools')
    parser.add_argument('--call-tool', action='store_true', help='Call code_context through Codex app-server without starting a model turn')
    args = parser.parse_args()
    if os.name != 'posix': raise ValueError('The optional Codex verification controller requires POSIX containment')
    if not args.node or not args.codex: raise ValueError('Install Node.js and Codex first')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    record = dict(schema_version=1, status='incomplete', model_turns_started=0,
                  scope='Codex configuration parsing, MCP startup and tool discovery; not agent adoption')
    client = None
    try:
        with tempfile.TemporaryDirectory(prefix='wraith-codex-check-') as directory:
            command = [args.node,str(args.launcher.resolve()),'codex-config','--root',str(args.root.resolve())]
            if args.allow_read_tools: command.append('--allow-read-tools')
            config = subprocess.check_output(command, env=clean_env(), text=True, timeout=20)
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
            if args.allow_read_tools:
                resolved = client.call('config/read',dict(includeLayers=False),timeout=20)
                settings = resolved['config']['mcp_servers']['wraith_context']['tools']
                modes = {name:settings[name]['approval_mode'] for name in tools}
                if any(mode!='approve' for mode in modes.values()): raise ValueError('Explicit read-tool approval configuration did not resolve')
                record['read_tool_approval_modes'] = modes
            if args.call_tool:
                thread = client.call('thread/start',dict(cwd=str(args.root.resolve()),ephemeral=True,
                    approvalPolicy='never',sandbox='read-only'),timeout=30)
                response = client.call('mcpServer/tool/call',dict(threadId=thread['thread']['id'],
                    server='wraith_context',tool='code_context',arguments=dict(query='canAccessProject expired trial')),timeout=30)
                payload = response.get('structuredContent')
                if not payload:
                    payload = json.loads(next(item['text'] for item in response['content'] if item.get('type')=='text'))
                record.update(tool_result_status=payload.get('status'),result_count=len(payload.get('results',[])))
                if response.get('isError') or payload.get('status')!='ok' or not payload.get('results'):
                    raise ValueError('Codex-dispatched tool returned no complete context')
                record.update(codex_dispatched_tool='code_context',result_count=len(payload['results']),
                    scope='Codex host-dispatched MCP call; no model turn or voluntary agent use')
            client.close();client=None
    except BaseException as exc:
        record['error'] = type(exc).__name__+': '+str(exc)
        raise
    finally:
        if client: client.close()
        (output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:record[k] for k in ['status','codex_version','tools','model_turns_started','scope']},indent=2))


if __name__ == '__main__': main()
