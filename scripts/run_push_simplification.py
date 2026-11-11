#!/usr/bin/env python3
"""Bounded, once-only pilot with source checks and native evidence audit."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from roborag.episode_files import read_json, read_jsonl, write_json
from roborag.episode_batch import protocol_sources, resource_sample
from roborag.rag_tasks import prompt_for
from roborag.push_simplification import FIXED_PACKAGE, prompt_for_profile, workflow_for_profile
from audit_push_t_current import audit_case, counts, costs

PROTOCOL = ROOT / "experiments/push_T/simplification-pilot-20261111.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze_sources(protocol):
    bank=ROOT/protocol['task']['bank']
    sources=protocol_sources(bank)
    paths=[PROTOCOL, FIXED_PACKAGE, ROOT/'local.runtime.json', Path(os.environ['COMPARE_CODEX_BIN'])]
    paths+=list((ROOT/'scripts').glob('*.py'))
    native=Path(json.loads((ROOT/'local.runtime.json').read_text())['upstream'])/'third_party/RoboDojo'
    paths+=list((native/'task/RoboDojo').rglob('*.py'))
    paths+=list((native/'task/RoboDojo/config').glob('*.yml'))
    paths+=list((native/'env_cfg').rglob('*.yml'))
    paths+=list((native/'src/eval_client').rglob('*.py'))
    for case in protocol['cases']:
        task='push_T'+('_random' if case['variant']=='random' else '')
        paths.append(ROOT/f"data/Assets/Eval_Layout/RoboDojo/arx_x5/{case['seed']}/{task}_{case['layout']}.json")
    for path in (bank/'graphs').glob('*.json'):
        graph=read_json(path);source=ROOT/'data'/graph['source']['path']
        assert sha(source)==graph['source']['sha256']
        paths.append(source)
    sources.update({str(p.resolve()):sha(p) for p in paths})
    return sources


def audit_record(record, freeze):
    profile=record['profile']
    profile_freeze=dict(freeze,prompt_sha256=freeze['prompts'][profile])
    row=audit_case(record,profile_freeze)
    calls,_=read_jsonl(Path(record['output'])/'mcp-calls.jsonl')
    commands,_=read_jsonl(Path(record['output'])/'commands.jsonl')
    ik,_=read_jsonl(Path(record['output'])/'ik-continuity.jsonl')
    run=read_json(Path(record['output'])/'run.json')
    assert run['args']['push_simplification']==profile
    row.update(profile=profile,legacy_workflow_verified=row['workflow_verified'],
        workflow_verified=workflow_for_profile(calls,profile),
        ik_rejections=sum(x.get('accepted') is False for x in ik),
        planar_checks=sum(x.get('request',{}).get('planar_measure',{}).get('command')=='planar_check' for x in commands),
        home_calls=sum(any(w.get('home') for w in x['request'].get('chunk',[])) for x in commands))
    if row['steps'] is not None:assert row['steps']<=600
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args()
    protocol=read_json(PROTOCOL);tag=protocol['tag'];out=ROOT/'runs'/tag
    report=ROOT/'results'/f'{tag}.json'
    if args.audit_only:
        freeze=read_json(out/'freeze.json');state=read_json(out/'status.json')
        assert all(sha(p)==h for p,h in freeze['source_sha256'].items())
        rows=[audit_record(r,freeze) for r in state['finished']]
        write_report(report,protocol,freeze,state,rows)
        return
    out.mkdir(parents=True,exist_ok=False)
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT,text=True).strip():
        raise RuntimeError('Commit experiment source before launch')
    runtime=read_json(ROOT/'local.runtime.json')
    sources=freeze_sources(protocol)
    freeze=dict(candidate_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        protocol=str(PROTOCOL),protocol_sha256=sha(PROTOCOL),source_sha256=sources,
        task=protocol['task'],conditions=protocol['conditions'],
        prompts={p:hashlib.sha256(prompt_for_profile(prompt_for(ROOT,'push_T','delta'),p).encode()).hexdigest()
                 for p in protocol['profiles']})
    write_json(out/'freeze.json',freeze)
    pending=[dict(profile=p,**c) for p in protocol['profiles'] for c in protocol['cases']]
    active={};finished=[];rows=[];blocked=False;started=time.monotonic()
    state=dict(pid=os.getpid(),candidate_commit=freeze['candidate_commit'],complete=False,
               phase='running',pending=pending,active={},finished=finished)
    write_json(out/'status.json',state)
    def interrupt(signum,frame):raise KeyboardInterrupt(f'Signal {signum}')
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    with (out/'driver.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            while pending or active:
                for key,(proc,log,record) in list(active.items()):
                    if proc.poll() is None:continue
                    log.close();record.update(returncode=proc.returncode,ended_epoch=time.time(),
                                             result=read_json(Path(record['output'])/'result.json'))
                    finished.append(record);del active[key]
                    try:
                        row=audit_record(record,freeze);rows.append(row)
                        if row['success'] is None or not row['workflow_verified'] or row['trajectory_problems']:blocked=True
                        print(json.dumps(dict(case=key,success=row['success'],steps=row['steps'],workflow=row['workflow_verified'])),flush=True)
                    except Exception as exc:
                        blocked=True
                        write_json(out/f'{key}-audit-error.json',dict(error=type(exc).__name__,detail=str(exc)))
                if blocked and not active:break
                pair_ready=all((Path(r['output'])/'ready.json').exists() for _,_,r in active.values())
                same_profile=not active or all(r['profile']==pending[0]['profile'] for _,_,r in active.values()) if pending else False
                if pending and not blocked and len(active)<2 and pair_ready and same_profile:
                    sample=resource_sample(active)
                    if int(sample['gpu'].split(',')[0])>=11000:
                        if freeze_sources(protocol)!=sources:raise RuntimeError('Frozen source drift')
                        c=pending.pop(0);key=f"{c['profile']}-seed{c['seed']}-{c['variant']}-l{c['layout']}"
                        directory=out/key
                        command=[runtime['policy_python'],'-m','roborag.rag_runner','--task','push_T',
                            '--variant',c['variant'],'--seed',str(c['seed']),'--layout',str(c['layout']),
                            '--output',str(directory),'--bank',str(ROOT/protocol['task']['bank']),
                            '--controller','delta','--model',protocol['conditions']['model'],
                            '--effort',protocol['conditions']['effort'],'--max-wall-seconds','5400',
                            '--push-simplification',c['profile']]
                        log=(out/f'{key}.log').open('w')
                        env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
                        proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                        record=dict(**c,output=str(directory),pid=proc.pid,started_epoch=time.time(),command=command)
                        active[key]=(proc,log,record)
                        print(json.dumps(dict(started=key,pid=proc.pid)),flush=True)
                state.update(pending=pending,active={k:r for k,(_,_,r) in active.items()},finished=finished,
                    phase='needs_review' if blocked else 'running',wall_seconds=time.monotonic()-started)
                write_json(out/'status.json',state)
                write_report(report,protocol,freeze,state,rows)
                if pending or active:time.sleep(5)
            if freeze_sources(protocol)!=sources:raise RuntimeError('Frozen source drift at closure')
            state.update(complete=not pending and not active and not blocked,phase='needs_review' if blocked else 'complete',
                         pending=pending,active={},finished=finished,wall_seconds=time.monotonic()-started)
            write_json(out/'status.json',state);write_report(report,protocol,freeze,state,rows)
        except BaseException as exc:
            state.update(phase='interrupted',error=type(exc).__name__,detail=str(exc),wall_seconds=time.monotonic()-started)
            write_json(out/'status.json',state)
            raise
        finally:
            for proc,log,record in active.values():
                if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
            for proc,log,record in active.values():
                try:proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                log.close()


def write_report(path,protocol,freeze,state,rows):
    write_json(path,dict(schema='push-t-simplification-pilot-results-v1',candidate_commit=freeze['candidate_commit'],
        complete=state.get('complete',False),phase=state['phase'],protocol=str(PROTOCOL),
        groups={p:dict(counts=counts([r for r in rows if r['profile']==p]),
                       costs=costs([r for r in rows if r['profile']==p])) for p in protocol['profiles']},
        cases=rows,pending=state.get('pending',[]),active=state.get('active',{}),
        interpretation=protocol['scope'],actual_billed_usd=None))


if __name__=='__main__':main()
