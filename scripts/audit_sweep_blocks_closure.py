"""Independent native/dispatch/process closure; read-only until writing a new report."""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def records(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def key(row):
    return row['seed'], row['variant'], row['layout']


def confirmed_feature_calls(calls, allow_incomplete=False):
    """Count only direct final expressions with the helper's returned evidence."""
    starts = [c for c in calls if c['tool'] == 'python_cell_start']
    ends = [c for c in calls if c['tool'] == 'python_cell']
    assert len(starts) >= len(ends) and (allow_incomplete or len(starts) == len(ends)), 'Unpaired cells in a scored run'
    confirmed, unclassified = [], []
    for start, end in zip(starts, ends):
        code, result = start['request']['code'], end['result']
        assert start['result']['step'] == result['step_before']
        if 'move_feature' not in code:
            continue
        try:
            last = ast.parse(code).body[-1]
            expression = last.value if isinstance(last, ast.Expr) else None
            function = expression.func if isinstance(expression, ast.Call) else None
            direct = (isinstance(function, ast.Attribute) and function.attr in ('move_feature', 'move_features')
                      and isinstance(function.value, ast.Name) and function.value.id == 'robo')
            value = ast.literal_eval(result.get('value') or 'None')
        except (ValueError, SyntaxError):
            direct, value = False, None
        if (direct and not result.get('error') and isinstance(value, dict)
                and 'feature_predictions' in value and value['execution']['action_steps'] > 0):
            assert value['execution']['action_steps'] <= result['action_steps']
            assert value['execution'] in result.get('motions', []), 'Feature receipt absent from parent motion ledger'
            confirmed.append(dict(cell=result['cell'], cell_step_before=result['step_before'],
                                  cell_step_after=result['step_after'], step_after=value['execution']['step'],
                                  step_before=value['execution']['step']-value['execution']['action_steps'],
                                  action_steps=value['execution']['action_steps'],
                                  motion_stopped=result.get('motion_stopped', False), helper=function.attr,
                                  source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                                  feature_predictions=value['feature_predictions']))
        else:
            unclassified.append(result['cell'])
    return dict(confirmed_direct_calls=len(confirmed), calls=confirmed,
                incomplete_cell_starts=len(starts)-len(ends),
                source_mentions_without_confirmation=unclassified,
                interpretation='Confirmed invocations, not evidence that the rigid-grasp assumption held. Unclassified mentions are not counted as calls.')


def audit_native_guard(directory, actions, commands):
    guard_path = directory/'ik-continuity.jsonl'
    events = records(guard_path)
    accepted = [event for event in events if event['accepted']]
    rejected = [event for event in events if not event['accepted']]
    delta_rows = [action for action in actions if 'delta_row' in action]
    assert [event['attempted_step'] for event in accepted] == [action['step'] for action in delta_rows]
    for event in accepted:
        assert len(event['checks']) == 2
        for check in event['checks']:
            assert check['passed'] and check['limit_rad'] == .25
            assert check['max_current_delta_rad'] <= .25 + 1e-9
            assert check.get('max_target_delta_rad', 0) <= .25 + 1e-9
    receipts = [command['result'] for command in commands if command['result'].get('rejection')]
    assert all(not receipt['rejection']['rejected_action_executed'] for receipt in receipts)
    assert Counter(event['attempted_step'] for event in rejected) == Counter(receipt['step']+1 for receipt in receipts)
    return dict(journal=str(guard_path), journal_sha256=digest(guard_path),
                accepted_delta_rows=len(accepted), rejected_attempts=len(rejected),
                rejected_receipts_verified=len(receipts),
                violation_counts=dict(Counter(check['error'] for event in rejected
                                              for check in event['checks'] if not check['passed'])))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('tag')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    batch = root/'runs'/args.tag
    status = read(batch/'status.json')
    driver_path = root/'runs'/f'{args.tag}-driver.json'
    driver = read(driver_path)
    if not status['complete'] or status['active'] or status['pending']:
        print(json.dumps(dict(ready_for_closure=False, phase=driver['phase'],
                              finished=len(status['finished']), active=list(status['active']), pending=len(status['pending']))))
        return
    assert driver['phase'] == 'complete', driver
    freeze_path = root/'runs'/f'{args.tag}-freeze.json'
    freeze = read(freeze_path)
    for path, sha in freeze['source_sha256'].items():
        assert digest(path) == sha, ('frozen source drift', path)
    protocol = read(freeze['protocol'])
    cases = read(root/freeze['task']['cases_file'])
    assert Counter(map(key, cases)) == Counter(map(key, status['finished']))
    report_path = Path(driver['report'])
    report = read(report_path)
    assert report['complete'] and report['audit']['passed']
    assert report['candidate_commit'] == freeze['candidate_commit']
    audited = {key(row): row for row in report['cases']}
    assert set(audited) == set(map(key, cases))
    baseline_path = root/'results/sweep-blocks-baseline-and-references-20261106.json'
    baseline = read(baseline_path)
    assert digest(baseline['sealed_audit']) == baseline['sealed_audit_sha256']
    for row in baseline['rows']:
        if row['native_result']:
            assert digest(row['native_result']) == row['native_sha256']
    old = {key(row): row for row in baseline['rows']}
    pids = {driver['pid'], driver['batch_pid']}
    births = set()
    for sample in records(batch/'resources.jsonl'):
        for group in sample.get('owned_processes', {}).values():
            for process in group:
                pids.add(process['pid'])
                births.add((process['pid'], process['started_epoch']))
    workspaces, rows = [], []
    for entry in status['finished']:
        directory = Path(entry['output']).resolve()
        assert directory.parent == batch.resolve()
        run = read(directory/'run.json')
        assert run['git_commit'] == freeze['candidate_commit']
        assert key(run['args']) == key(entry)
        assert digest(directory/'agent-prompt.txt') == freeze['prompt_sha256'] == run['prompt_sha256']
        for path, sha in run['source_sha256'].items():
            assert freeze['source_sha256'][str(Path(path).resolve())] == sha
        pids.add(entry['pid'])
        for name in ('process.json', 'agent-process.json'):
            if (directory/name).exists():
                pids.update(v for k, v in read(directory/name).items() if k.endswith('pid'))
        if (directory/'agent-workspace.json').exists():
            workspaces.append(read(directory/'agent-workspace.json')['path'])
        row = audited[key(entry)]
        for path, sha in row['artifact_sha256'].items():
            assert digest(path) == sha, ('attempt evidence changed', path)
        ready = read(directory/'ready.json') if (directory/'ready.json').exists() else None
        if ready:
            assert ready['step_limit'] == 1000 and ready.get('execution_guard') == protocol['conditions']['execution_guard']
        raw = list(directory.rglob('_result.json'))
        assert len(raw) <= 1
        detail = {name: row[name] for name in ('seed','variant','layout','success','native_score','steps','steps_complete','wall_seconds','usage','native_result','native_sha256')}
        if row['success'] is not None:
            assert len(raw) == 1 and digest(raw[0]) == row['native_sha256']
            native = read(raw[0])
            assert native['eval_time'] == 1 and not native.get('policy_error')
            assert native['details']['0']['layout_id'] == row['layout']
            assert native['details']['0']['success'] is row['success']
            assert (native['success_rate'] == 1) is row['success']
            assert native['score'] == row['native_score']
            actions = records(directory/'actions.jsonl')
            commands = records(directory/'commands.jsonl')
            assert len(actions) == sum(c['result'].get('action_steps',0) for c in commands) == row['steps'] <= 1000
            assert row['steps_complete'] and row['workflow_verified']
            detail['independent_action_rows_verified'] = len(actions)
            if protocol['conditions']['execution_guard']:
                detail['native_guard_audit'] = audit_native_guard(directory, actions, commands)
        calls = records(directory/'mcp-calls.jsonl') if (directory/'mcp-calls.jsonl').exists() else []
        assert not any(c['tool'] == 'measure_mug_geometry' for c in calls), 'Hang-only tool exposed to sweep'
        holds = [c['result']['result'] for c in calls if c['tool'] == 'hold_joints']
        cells = [c['result'] for c in calls if c['tool'] == 'python_cell']
        detail.update(tool_counts=dict(Counter(c['tool'] for c in calls)),
                      joint_hold_calls=len(holds), joint_hold_steps=sum(h['action_steps'] for h in holds),
                      completed_cells=len(cells), cells_with_errors=sum(bool(c.get('error')) for c in cells),
                      truncated_or_stopped_cells=sum(bool(c.get('motion_stopped')) for c in cells),
                      feature_helper_trace=confirmed_feature_calls(calls, allow_incomplete=row['success'] is None),
                      cell_source_mentions_move_feature=sum('move_feature' in c['request']['code'] for c in calls if c['tool']=='python_cell_start'),
                      helper_usage_note='Source mentions are not an invocation count; confirm executed control paths before attributing outcomes.')
        if key(row) in old:
            previous = old[key(row)]
            detail['historical_same_scene'] = {k:previous[k] for k in ('success','native_score','steps','native_result','native_sha256')}
        rows.append(detail)
    boot = int(next(x.split()[1] for x in Path('/proc/stat').read_text().splitlines() if x.startswith('btime ')))
    hz = os.sysconf('SC_CLK_TCK')
    live, reused = [], []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            cmd = (proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace').strip()
            stat = (proc/'stat').read_text().rsplit(')',1)[1].split()
            birth = boot+int(stat[19])/hz
        except (FileNotFoundError,PermissionError,ProcessLookupError):
            continue
        if not cmd:
            continue
        pid = int(proc.name)
        known = [t for p,t in births if p == pid]
        same = pid in pids and (not known or any(abs(birth-t)<.1 for t in known))
        related = str(batch.resolve()) in cmd or any(w in cmd for w in workspaces)
        if same or related:
            live.append(dict(pid=pid,started_epoch=birth,command=cmd))
        elif pid in pids:
            reused.append(dict(pid=pid,started_epoch=birth))
    assert not live, live
    closed = dict(checked_at=datetime.now(timezone.utc).isoformat(), complete=True, tag=args.tag,
                  root=str(root), candidate_commit=freeze['candidate_commit'],
                  protocol=freeze['protocol'], protocol_sha256=digest(freeze['protocol']),
                  report=str(report_path), report_sha256=digest(report_path), freeze_sha256=digest(freeze_path),
                  driver_sha256=digest(driver_path), frozen_sources_verified=len(freeze['source_sha256']),
                  baseline_native_reports_preserved=sum(bool(r['native_result']) for r in baseline['rows']),
                  registered_pids=sorted(pids), registered_process_identities=len(births),
                  policy_workspaces_checked=workspaces, reused_pid_numbers=reused, live_related_processes=live,
                  rows=rows, counts=report['counts'], costs=report['all_attempt_costs'],
                  batch_wall_seconds=report['batch_wall_seconds'], actual_billed_usd=None,
                  interpretation=protocol['scope']['interpretation'])
    assert not args.output.exists(), 'Do not overwrite closure evidence'
    args.output.write_text(json.dumps(closed,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:closed[k] for k in ('complete','counts','frozen_sources_verified','live_related_processes')}))


if __name__ == '__main__':
    main()
