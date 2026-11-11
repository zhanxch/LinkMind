"""Run one explicitly authorized supplement of missing native scores only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from roborag.episode_files import write_json
from roborag.rag_tasks import prompt_for


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def key(row):
    return row['seed'], row['variant'], row['layout']


def verify_gate(gate):
    for name in ['report', 'closure', 'freeze']:
        assert digest(gate[name]) == gate[name+'_sha256'], (name, gate['tag'])
    report, closure, freeze = (read(gate[name]) for name in ['report', 'closure', 'freeze'])
    state = read(Path(gate['root'])/'runs'/gate['tag']/'status.json')
    assert state['complete'] and not state['active'] and not state['pending']
    assert report['complete'] and report['audit']['passed'] and closure['complete']
    assert not closure['live_related_processes']
    assert report['candidate_commit'] == closure['candidate_commit'] == freeze['candidate_commit'] == gate['candidate_commit']
    assert report['counts'] == closure['counts'] == gate['counts']
    assert report['counts']['attempts_closed'] == 50
    assert closure['report_sha256'] == digest(gate['report'])
    assert closure['freeze_sha256'] == digest(gate['freeze'])
    for path, sha in freeze['source_sha256'].items():
        assert digest(path) == sha, ('frozen source changed', path)
    artifacts, native = 0, 0
    for row in report['cases']:
        for path, sha in row['artifact_sha256'].items():
            assert digest(path) == sha, ('original attempt changed', path)
            artifacts += 1
        if row['native_result']:
            assert digest(row['native_result']) == row['native_sha256']
            native += 1
    return report, freeze, dict(tag=gate['tag'], frozen_sources=len(freeze['source_sha256']),
                                attempt_artifacts=artifacts, native_reports=native)


def preflight(protocol):
    assert len(protocol['tasks']) == 1
    task = protocol['tasks'][0]
    assert task['task'] in ['hang_mugs', 'sweep_blocks']
    parent = protocol['parent_batch']
    report, freeze, parent_evidence = verify_gate(parent)
    assert Path(parent['root']).resolve() == ROOT
    assert protocol['base_commit'] == parent['candidate_commit']
    assert protocol['conditions'] == freeze['conditions']
    cases = read(ROOT/task['cases_file'])
    expected = [{name: row[name] for name in ['seed', 'variant', 'layout']}
                for row in report['cases'] if row['success'] is None]
    assert cases == expected and len(cases) > 0, 'Only originally unscored scenes are eligible'
    assert len(cases) == task['case_count'] == protocol['planned_native_attempts']
    assert len(set(map(key, cases))) == len(cases)
    for field in ['task', 'bank', 'native_step_limits', 'preflight_file']:
        assert task[field] == freeze['task'][field]
    for row in report['cases']:
        if row['success'] is None:
            assert row['native_result'] is None
            assert not list(Path(row['directory']).rglob('_result.json'))
    gates = [parent_evidence]
    for gate in protocol['required_closed_batches']:
        assert gate['tag'] != parent['tag']
        _, _, evidence = verify_gate(gate)
        gates.append(evidence)
    subprocess.run(['git', 'diff', '--exit-code', parent['candidate_commit'], '--', 'src', 'prompts', 'tests'], cwd=ROOT, check=True)
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', 'src', 'prompts', 'tests'], cwd=ROOT, text=True).strip()
    prompt_sha = hashlib.sha256(prompt_for(ROOT, task['task'], 'delta').encode()).hexdigest()
    assert prompt_sha == freeze['prompt_sha256']
    binary = Path(os.environ['COMPARE_CODEX_BIN']).resolve()
    assert digest(binary) == freeze['source_sha256'][str(binary)]
    bank = read(ROOT/task['preflight_file'])
    assert bank['passed'] and bank['task'] == task['task']
    assert Path(bank['bank']).resolve() == (ROOT/task['bank']).resolve()
    for path, sha in {**bank['metadata_sha256'], **bank['source_sha256']}.items():
        assert digest(path) == sha, path
    for case in cases:
        suffix = '_random' if case['variant'] == 'random' else ''
        scene = (ROOT/'data/Assets/Eval_Layout/RoboDojo/arx_x5'/str(case['seed'])/f'{task["task"]}{suffix}_{case["layout"]}.json').resolve()
        assert digest(scene) == freeze['source_sha256'][str(scene)]
    active = []
    names = {'run_generalization_task.py', 'run_rag_mcp.py', 'run_sweep_blocks_validation.py',
             'run_hang_mugs_full50.py', 'run_hang_mugs_tools_validation.py', 'run_unscored_supplement.py'}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        if any(Path(arg).name in names or arg == 'roborag.rag_sim' for arg in args):
            active.append(dict(pid=int(proc.name), command=args))
    assert not active, ('Another native batch is still active', active)
    free = [int(line) for line in subprocess.check_output(['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], text=True).splitlines()]
    assert free[0] >= protocol['resource_policy']['minimum_free_gpu_mib']
    return dict(passed=True, task=task['task'], case_count=len(cases), cases=cases,
                parent_sources_and_reports=gates, prompt_sha256=prompt_sha,
                conditions_identical_to_parent=True, runtime_and_prompts_identical_to_parent=True,
                gpu_free_mib=free, active_related_native_processes=active)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    assert Path(args.tag).name == args.tag
    protocol_path = args.protocol.resolve()
    protocol = read(protocol_path)
    checked = preflight(protocol)
    if args.check:
        print(json.dumps(checked, ensure_ascii=False))
        return
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True).strip(), 'Commit this registration before launch'
    path = ROOT/'runs'/f'{args.tag}-driver.json'
    report_path = ROOT/'results'/f'{args.tag}.json'
    assert not any(p.exists() for p in [path, ROOT/'runs'/args.tag, ROOT/'runs'/f'{args.tag}-freeze.json', ROOT/'runs'/f'{args.tag}-launch.json', report_path]), 'Attempt exists; never restart it'
    state = dict(pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(), phase='launching',
                 tag=args.tag, preflight=checked, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 start_ticks=int(Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]))
    write_json(path, state)
    task = protocol['tasks'][0]['task']
    process = subprocess.Popen([sys.executable, '-u', str(ROOT/'scripts/run_generalization_task.py'),
                                '--task', task, '--tag', args.tag, '--protocol', str(protocol_path)], cwd=ROOT, start_new_session=True)
    state.update(phase='running', batch_pid=process.pid)
    write_json(path, state)
    def stop(*_):
        if process.poll() is None:
            process.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    code = process.wait()
    state.update(phase='auditing', batch_returncode=code)
    write_json(path, state)
    audit = subprocess.run([sys.executable, str(ROOT/'scripts'/f'audit_{task}_results.py'), '--tag', args.tag,
                            '--protocol', str(protocol_path), '--output', str(report_path)], cwd=ROOT)
    report = read(report_path) if report_path.exists() else {}
    complete = code == 0 and audit.returncode == 0 and report.get('complete') and report.get('audit', {}).get('passed') and report.get('counts', {}).get('attempts_closed') == protocol['planned_native_attempts']
    state.update(phase='complete' if complete else 'needs_review', audit_returncode=audit.returncode,
                 report=str(report_path), counts=report.get('counts'), ended_at=datetime.now(timezone.utc).isoformat())
    write_json(path, state)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
