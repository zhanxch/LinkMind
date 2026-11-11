"""Run one complete first pass of the accepted hang-mug candidate."""
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
sys.path.insert(0, str(ROOT / 'src'))
from roborag.episode_files import write_json
from roborag.rag_tasks import prompt_for

TAG = 'hang-mugs-guard-v2-full50-20261105'
BASE = '8a954e3b8dc01fb99fbe57a60e968fa917ad832d'
PROTOCOL = ROOT / 'experiments/hang_mugs/guard-v2-full50-20261105.json'


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def preflight():
    protocol = read(PROTOCOL)
    assert protocol['base_commit'] == BASE
    task = protocol['tasks'][0]
    expected = [dict(variant=v, layout=l, seed=1)
                for l in range(25) for v in ('standard', 'random')]
    assert task['task'] == 'hang_mugs'
    assert task['case_count'] == protocol['planned_native_attempts'] == 50
    assert task['native_step_limits'] == dict(standard=800, random=800)
    assert read(ROOT/task['cases_file']) == expected
    parent = protocol['development_batch']
    for name in ('report', 'closure', 'freeze'):
        assert digest(parent[name]) == parent[name+'_sha256'], name
    closure, freeze = read(parent['closure']), read(parent['freeze'])
    assert closure['complete'] and not closure['live_related_processes']
    assert closure['counts']['attempts_closed'] == 3
    assert closure['candidate_commit'] == freeze['candidate_commit'] == BASE
    status = read(ROOT/'runs'/parent['tag']/'status.json')
    assert status['complete'] and not status['active'] and not status['pending']
    assert protocol['conditions'] == freeze['conditions']
    for path, sha in freeze['source_sha256'].items():
        assert digest(path) == sha, path
    for row in closure['rows']:
        assert digest(row['native_result']) == row['native_sha256']
    prompt_sha = hashlib.sha256(prompt_for(ROOT, 'hang_mugs', 'delta').encode()).hexdigest()
    assert prompt_sha == freeze['prompt_sha256']
    subprocess.run(['git', 'diff', '--exit-code', BASE, '--', 'src', 'prompts'], cwd=ROOT, check=True)
    assert not subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all', '--', 'src', 'prompts'], cwd=ROOT, text=True)
    for case in expected:
        suffix = '_random' if case['variant'] == 'random' else ''
        path = ROOT/'data/Assets/Eval_Layout/RoboDojo/arx_x5/1'/f'hang_mugs{suffix}_{case["layout"]}.json'
        read(path)
    return dict(accepted_runtime_commit=BASE, development_sources_verified=len(freeze['source_sha256']),
                scene_files_verified=50, prompt_sha256=prompt_sha)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Validate registration without launching')
    args = parser.parse_args()
    checked = preflight()
    if args.check:
        print(json.dumps(checked))
        return
    path = ROOT/'runs'/f'{TAG}-driver.json'
    assert not any(p.exists() for p in (path, ROOT/'runs'/TAG, ROOT/'runs'/f'{TAG}-freeze.json')), 'Attempt already exists'
    free = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], text=True)
    assert int(free.splitlines()[0]) >= 11000, 'Insufficient free GPU memory'
    state = dict(pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(),
                 phase='launching', tag=TAG, preflight=checked)
    write_json(path, state)
    process = subprocess.Popen([sys.executable, '-u', str(ROOT/'scripts/run_generalization_task.py'),
                                '--task', 'hang_mugs', '--tag', TAG, '--protocol', str(PROTOCOL)],
                               cwd=ROOT, start_new_session=True)
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
    report_path = ROOT/'results'/f'{TAG}.json'
    audit = subprocess.run([sys.executable, str(ROOT/'scripts/audit_hang_mugs_results.py'),
                            '--tag', TAG, '--protocol', str(PROTOCOL), '--output', str(report_path)], cwd=ROOT)
    report = read(report_path) if report_path.exists() else {}
    complete = (code == 0 and audit.returncode == 0 and report.get('complete') and
                report.get('audit', {}).get('passed') and report.get('counts', {}).get('attempts_closed') == 50)
    state.update(phase='complete' if complete else 'needs_review', audit_returncode=audit.returncode,
                 report=str(report_path), counts=report.get('counts'), ended_at=datetime.now(timezone.utc).isoformat())
    write_json(path, state)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
