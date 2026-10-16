"""Deliberate checkout-isolation control on public repositories, not a discovery."""
import json
import shutil
import subprocess
from pathlib import Path
from mcp_client import Client, clean_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main():
    root = (REPO/'.wraith/code-context-study').resolve()
    output = root/'worktree-controls'; output.mkdir(exist_ok=False)
    rows = []
    for item in json.loads((HERE/'protocol.json').read_text())['repositories']:
        for state in ['primary', 'parallel']:
            folder = output/(item['name']+'-'+state)
            subprocess.run(['git','-c','core.hooksPath=','-C',str(root/item['name']),
                            'worktree','add','--detach',str(folder),item['commit']],
                           env=clean_env(),capture_output=True,check=True)
            (folder/'wraith_context_control.ts').write_text(f'export function contextWitness() {{ return "{state}-dirty"; }}\n')
            (folder/'.serena').mkdir()
            (folder/'.serena/project.yml').write_text(f'project_name: {item["name"]}-{state}\nlanguage_servers:\n- typescript\nencoding: utf-8\n')
            native = subprocess.check_output(['rg','-n','contextWitness','wraith_context_control.ts'],cwd=folder,env=clean_env(),text=True)
            record = dict(repository=item['name'],state=state,classification='deliberate dirty-worktree control',
                          native_pass=(state+'-dirty') in native)
            for lane in ['candidate','serena']:
                client = None
                try:
                    if lane == 'candidate':
                        command = [shutil.which('node'),str(HERE.parent/'cli.cjs'),'mcp','--root',str(folder),'--cache',str(output/'cache')]
                        name,args='code_symbols',dict(query='contextWitness')
                    else:
                        command = [str(root/'serena-venv/bin/serena'),'start-mcp-server','--project',str(folder),
                                   '--context','ide','--mode','planning','--mode','no-onboarding','--agent-interface','tools',
                                   '--enable-web-dashboard','false','--open-web-dashboard','false','--enable-gui-log-window','false']
                        name,args='find_symbol',dict(name_path_pattern='contextWitness',relative_path='wraith_context_control.ts',include_body=True)
                    client = Client(command,folder,clean_env({'SERENA_HOME':str(root/'serena-home-ready'),'SERENA_USAGE_REPORTING':'false'}))
                    client.initialize()
                    result = client.call('tools/call',dict(name=name,arguments=args))
                    serialized = json.dumps(result)
                    record[lane+'_pass'] = not result.get('isError') and (state+'-dirty') in serialized and (('parallel' if state=='primary' else 'primary')+'-dirty') not in serialized
                    (output/(item['name']+'-'+state+'-'+lane+'.json')).write_text(json.dumps(result,indent=2)+'\n')
                except Exception as exc:
                    record[lane+'_error']=str(exc);record[lane+'_pass']=False
                finally:
                    if client:client.close()
            rows.append(record)
            print(item['name'],state,{k:v for k,v in record.items() if k.endswith('_pass')},flush=True)
    (output/'summary.json').write_text(json.dumps(dict(schema_version=1,results=rows,
         interpretation='Seeded isolation control, not a natural defect, agent-completion result or adoption evidence.'),indent=2)+'\n')


if __name__=='__main__':
    main()
