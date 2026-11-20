#!/usr/bin/env python3
"""User-run one-time setup. Never invoked by scientific subagents."""
import argparse,json,os,subprocess,sys,venv
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def run(args):
    print('>', ' '.join(map(str,args)),flush=True)
    p=subprocess.run([str(x) for x in args],cwd=R)
    if p.returncode:raise SystemExit(p.returncode)
def main():
    a=argparse.ArgumentParser();a.add_argument('--corpus',required=True);a.add_argument('--workbook');a.add_argument('--skip-install',action='store_true');args=a.parse_args()
    if sys.version_info[:2] not in ((3,11),(3,12),(3,13)):raise SystemExit('Use Python 3.11-3.13; the supplied release is tested on 3.12.')
    env=R/'.venv';py=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not py.exists():venv.EnvBuilder(with_pip=True).create(env)
    if not args.skip_install:run([py,'-m','pip','install','-r','requirements.txt'])
    config=R/'config/paths.yaml'
    if not config.exists():
        cmd=[py,'tools/tfm.py','configure','--corpus',args.corpus]
        if args.workbook:cmd+=['--workbook',args.workbook]
        run(cmd)
    else:print('Retaining existing config/paths.yaml; no configuration overwritten.',flush=True)
    for command in [['init'],['preflight'],['import-xlsx'],['check-columns'],['metadata-normalize'],['relations-import'],['dedup-seed'],['seed'],['validate','--scope','core'],['checkpoint'],['status']]:
        run([py,'tools/tfm.py',*command])
    report=R/'work/SETUP_REPORT.json';report.write_text(json.dumps({'status':'SETUP_COMPLETE','python':str(py),'corpus':args.corpus,'next':'Activate .venv, start claude, run /tfm-finalize'},indent=2),encoding='utf-8')
    print('\nSETUP_COMPLETE. Activate .venv, start claude from this project folder, then /tfm-finalize.',flush=True)
if __name__=='__main__':main()
