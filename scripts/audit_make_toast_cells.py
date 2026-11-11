#!/usr/bin/env python3
"""Verify a frozen development batch against native reports and public tool logs."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from roborag.episode_files import write_json


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path): return json.loads(Path(path).read_text())


def audit(tag):
    directory=ROOT/'runs'/tag
    freeze=read(directory.with_name(tag+'-freeze.json'))
    status=read(directory/'status.json')
    assert status['complete'] and not status['active'] and not status['pending']
    protocol=read(freeze['protocol'])
    config=freeze['task']; expected=read(ROOT/config['cases_file'])
    assert len(status['finished'])==len(expected)
    assert {(c['variant'],c['layout'],c['seed']) for c in expected}=={(c['variant'],c['layout'],c['seed']) for c in status['finished']}
    drift=[p for p,h in freeze['source_sha256'].items() if sha(p)!=h]
    assert not drift,drift
    rows=[]
    for entry in status['finished']:
        path=Path(entry['output']); run=read(path/'run.json'); ready=read(path/'ready.json')
        assert run['git_commit']==freeze['candidate_commit']
        assert run['prompt_sha256']==freeze['prompt_sha256']
        for key in ('variant','layout','seed'): assert run['args'][key]==entry[key]
        assert ready['step_limit']==1400
        if 'execution_guard' in protocol['conditions']:
            assert ready['execution_guard']==protocol['conditions']['execution_guard']
        for p,h in run['source_sha256'].items(): assert sha(p)==h,p
        calls=[json.loads(l) for l in (path/'mcp-calls.jsonl').read_text().splitlines()] if (path/'mcp-calls.jsonl').exists() else []
        tools=Counter(c['tool'] for c in calls)
        cells=[c['result'] for c in calls if c['tool']=='python_cell']
        row=dict(variant=entry['variant'],layout=entry['layout'],seed=entry['seed'],path=str(path),tool_counts=dict(tools),cell_count=len(cells),cell_action_steps=sum(c['action_steps'] for c in cells),cell_errors=sum(bool(c.get('error')) for c in cells))
        if (path/'result.json').exists():
            result=read(path/'result.json'); native=read(result['native_result'])
            assert native==result['native'] and sha(result['native_result'])==result['native_sha256']
            assert native['eval_time']==1 and not native.get('policy_error')
            assert result['native_control_steps']<=1400
            assert result['retrieval_before_plan_before_execution']
            row.update(outcome='success' if native['success_rate']==1 else 'failure',score=native['score'],native_result=result['native_result'],native_sha256=result['native_sha256'],steps=result['native_control_steps'],wall_seconds=result['wall_seconds'],usage=result['native_agent']['usage'])
        else:
            row.update(outcome='unscored',exit=read(path/'exit.json') if (path/'exit.json').exists() else None)
        commands=[json.loads(l) for l in (path/'commands.jsonl').read_text().splitlines()] if (path/'commands.jsonl').exists() else []
        row['joint_hold_steps']=sum(c['result']['action_steps'] for c in commands if 'joint_hold' in c['request'])
        guard=[json.loads(l) for l in (path/'ik-continuity.jsonl').read_text().splitlines()] if (path/'ik-continuity.jsonl').exists() else []
        row['native_ik_accepted_rows']=sum(c['accepted'] for c in guard)
        row['native_ik_rejected_rows']=sum(not c['accepted'] for c in guard)
        rows.append(row)
    return dict(complete=True,generated_at=datetime.now(timezone.utc).isoformat(),tag=tag,candidate_commit=freeze['candidate_commit'],protocol=freeze['protocol'],protocol_sha256=sha(freeze['protocol']),frozen_sources_checked=len(freeze['source_sha256']),counts=dict(Counter(r['outcome'] for r in rows)),rows=rows,batch_wall_seconds=status['wall_seconds'],actual_billed_usd=None,interpretation='Previously analysed development scenes; no held-out generalization, statistical or single-component causal claim. Unscored attempts remain separate.')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--tag',required=True); args=parser.parse_args()
    report=audit(args.tag); output=ROOT/'results'/f'{args.tag}.json'
    if output.exists(): raise RuntimeError('Audit already exists; preserve it and inspect before writing a new revision')
    write_json(output,report); print(json.dumps(dict(output=str(output),counts=report['counts'])))


if __name__=='__main__': main()
