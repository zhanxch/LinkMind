"""Independent closure of the registered supplement; never writes run records."""
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def records(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def key(row):
    return row['seed'], row['variant'], row['layout']


def verify_sources(freeze):
    for path, expected in freeze['source_sha256'].items():
        assert digest(path) == expected, ('source drift', path)
    return len(freeze['source_sha256'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    tag = 'make-toast-python-cells-full50-supplement-20261105'
    batch = root / 'runs' / tag
    status = read(batch / 'status.json')
    driver = read(root / 'runs' / f'{tag}-driver.json')
    if not status['complete'] or status['pending'] or status['active']:
        print(json.dumps(dict(ready_for_closure=False, phase=driver['phase'],
                              finished=len(status['finished']), active=list(status['active']),
                              pending=len(status['pending']))))
        return
    assert driver['phase'] == 'complete', driver
    freeze_path = root / 'runs' / f'{tag}-freeze.json'
    freeze = read(freeze_path)
    protocol = read(freeze['protocol'])
    declared = read(root / freeze['task']['cases_file'])
    assert len(declared) == len(status['finished']) == 3
    assert collections.Counter(map(key, declared)) == collections.Counter(map(key, status['finished']))
    assert freeze['candidate_commit'] == '7b9cec43b0ca38bdeea6c9f738a454c67c6f3938'
    current_sources = verify_sources(freeze)
    parent = protocol['parent_batch']
    for name in ('report', 'closure', 'freeze'):
        assert digest(parent[name]) == parent[name + '_sha256']
    parent_sources = verify_sources(read(parent['freeze']))
    original = read(parent['report'])
    assert original['counts'] == parent['counts']
    assert {key(r) for r in original['cases'] if r['success'] is None} == set(map(key, declared))
    for row in original['cases']:
        for path, expected in row['artifact_sha256'].items():
            assert digest(path) == expected, ('original attempt changed', path)
    report_path = root / 'results' / f'{tag}.json'
    report = read(report_path)
    assert report['complete'] and report['audit']['passed']
    assert report['candidate_commit'] == freeze['candidate_commit']
    audited = {key(r): r for r in report['cases']}
    assert set(audited) == set(map(key, declared))
    pids = {driver['pid'], driver['batch_pid']}
    births = set()
    for sample in records(batch / 'resources.jsonl'):
        for group in sample.get('owned_processes', {}).values():
            for process in group:
                pids.add(process['pid'])
                births.add((process['pid'], process['started_epoch']))
    workspaces = []
    rows = []
    for entry in status['finished']:
        directory = Path(entry['output']).resolve()
        assert directory.parent == batch.resolve()
        run = read(directory / 'run.json')
        assert run['git_commit'] == freeze['candidate_commit']
        assert key(run['args']) == key(entry)
        assert run['prompt_sha256'] == freeze['prompt_sha256']
        assert digest(directory / 'agent-prompt.txt') == freeze['prompt_sha256']
        for path, expected in run['source_sha256'].items():
            assert freeze['source_sha256'][str(Path(path).resolve())] == expected
        pids.add(entry['pid'])
        for name in ('process.json', 'agent-process.json'):
            if (directory / name).exists():
                pids.update(v for k, v in read(directory / name).items() if k.endswith('pid'))
        if (directory / 'agent-workspace.json').exists():
            workspaces.append(read(directory / 'agent-workspace.json')['path'])
        row = audited[key(entry)]
        for path, expected in row['artifact_sha256'].items():
            assert digest(path) == expected, ('supplement attempt changed', path)
        raw_paths = list(directory.rglob('_result.json'))
        assert len(raw_paths) <= 1
        evidence = dict(seed=entry['seed'], variant=entry['variant'], layout=entry['layout'],
                        success=row['success'], score=row['native_score'], steps=row['steps'],
                        steps_complete=row['steps_complete'], usage=row['usage'],
                        wall_seconds=row['wall_seconds'])
        if row['success'] is not None:
            assert len(raw_paths) == 1
            native = read(raw_paths[0])
            receipt = read(directory / 'result.json')
            assert native == receipt['native'] == entry['result']['native']
            assert digest(raw_paths[0]) == receipt['native_sha256'] == row['native_sha256']
            assert native['eval_time'] == 1 and not native.get('policy_error')
            assert native['details']['0']['layout_id'] == entry['layout']
            assert native['details']['0']['success'] is row['success']
            assert (native['success_rate'] == 1) is row['success']
            assert native['score'] == row['native_score']
            actions = records(directory / 'actions.jsonl')
            commands = records(directory / 'commands.jsonl')
            dispatched = sum(c['result'].get('action_steps', 0) for c in commands)
            assert len(actions) == dispatched == receipt['native_control_steps'] == row['steps']
            assert row['steps'] <= 1400 and row['steps_complete']
            assert receipt['retrieval_before_plan_before_execution']
            evidence.update(native_result=str(raw_paths[0]), native_sha256=digest(raw_paths[0]),
                            action_log_rows=len(actions), receipt_steps=dispatched)
        else:
            evidence.update(native_result_absent=not raw_paths,
                            failure=row['failure'], native_scoring_issues=row['native_scoring_issues'])
        rows.append(evidence)
    # PID number alone may be reused. Compare the identities saved by the resource log.
    boot = int(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines()
                    if line.startswith('btime ')))
    hz = os.sysconf('SC_CLK_TCK')
    live = []
    recycled = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            cmd = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace').strip()
            stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            birth = boot + int(stat[19]) / hz
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if not cmd:
            continue
        pid = int(proc.name)
        known = [t for p, t in births if p == pid]
        matched_identity = pid in pids and (not known or any(abs(birth - t) < .1 for t in known))
        related_command = str(batch.resolve()) in cmd or any(w in cmd for w in workspaces)
        if matched_identity or related_command:
            live.append(dict(pid=pid, started_epoch=birth, command=cmd))
        elif pid in pids:
            recycled.append(dict(pid=pid, started_epoch=birth))
    assert not live, live
    closed = dict(checked_at=datetime.now(timezone.utc).isoformat(), complete=True, tag=tag,
                  candidate_commit=freeze['candidate_commit'], protocol=freeze['protocol'],
                  protocol_sha256=digest(freeze['protocol']), report=str(report_path),
                  report_sha256=digest(report_path), freeze_sha256=digest(freeze_path),
                  frozen_sources_verified=current_sources, parent_frozen_sources_verified=parent_sources,
                  parent_original_attempts_preserved=len(original['cases']),
                  registered_pids=sorted(pids), registered_process_identities=len(births),
                  policy_workspaces_checked=workspaces, live_related_processes=live,
                  reused_pid_numbers=recycled, rows=rows, counts=report['counts'],
                  costs=report['all_attempt_costs'], batch_wall_seconds=status['wall_seconds'],
                  actual_billed_usd=None,
                  interpretation='Three separately registered missing-outcome attempts only; first-pass 13/34/3 and all original costs remain unchanged.')
    assert not args.output.exists(), 'Do not overwrite closure evidence'
    args.output.write_text(json.dumps(closed, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: closed[k] for k in ('complete', 'counts', 'frozen_sources_verified',
                                            'parent_original_attempts_preserved', 'live_related_processes')}))


if __name__ == '__main__':
    main()
