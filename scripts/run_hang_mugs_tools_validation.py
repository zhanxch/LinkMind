"""One registered three-scene development batch after the toast supplement closes."""
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

TAG = 'hang-mugs-tools-v1-dev-20261105'
PROTOCOL = ROOT / 'experiments/hang_mugs/tools-v1-development-20261105.json'


def main():
    global TAG, PROTOCOL
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', default=TAG)
    parser.add_argument('--protocol', type=Path, default=PROTOCOL)
    args = parser.parse_args()
    TAG, PROTOCOL = args.tag, args.protocol.resolve()
    protocol = json.loads(PROTOCOL.read_text())
    gate = protocol['toast_supplement_gate']
    closure_path = Path(gate['closure'])
    assert hashlib.sha256(closure_path.read_bytes()).hexdigest() == gate['closure_sha256']
    closure = json.loads(closure_path.read_text())
    assert closure['complete'] and not closure['live_related_processes']
    assert closure['counts']['attempts_closed'] == 3
    if 'predecessor_gate' in protocol:
        predecessor = protocol['predecessor_gate']
        previous_path = Path(predecessor['closure'])
        assert hashlib.sha256(previous_path.read_bytes()).hexdigest() == predecessor['closure_sha256']
        previous = json.loads(previous_path.read_text())
        assert previous['complete'] and not previous['live_related_processes']
        assert previous['candidate_commit'] == predecessor['candidate_commit']
    path = ROOT / 'runs' / f'{TAG}-driver.json'
    assert not any(p.exists() for p in (path, ROOT/'runs'/TAG, ROOT/'runs'/f'{TAG}-freeze.json')), 'Attempt already exists'
    state = dict(pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(), phase='launching', tag=TAG)
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
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    complete = (code == 0 and audit.returncode == 0 and report.get('complete') and
                report.get('audit', {}).get('passed') and report.get('counts', {}).get('attempts_closed') == 3)
    state.update(phase='complete' if complete else 'needs_review', audit_returncode=audit.returncode,
                 report=str(report_path), counts=report.get('counts'), ended_at=datetime.now(timezone.utc).isoformat())
    write_json(path, state)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
