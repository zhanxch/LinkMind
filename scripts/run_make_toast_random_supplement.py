#!/usr/bin/env python3
"""One separately registered supplement for a service-interrupted random case."""
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from roborag.episode_files import write_json
TAG='make-toast-reliability-v2-random-supplement-20261104'
PROTOCOL=ROOT/'experiments/make_toast/reliability-v2-random-supplement-20261104.json'


def main():
    previous=ROOT/'runs/make-toast-reliability-v2-dev-20261104'
    old_status=json.loads((previous/'status.json').read_text())
    if not old_status['complete'] or old_status['active'] or old_status['pending']:
        raise RuntimeError('Original three-case batch must finish before supplement')
    previous_driver=json.loads(previous.with_name(previous.name+'-driver.json').read_text())
    if previous_driver['phase'] != 'complete':
        raise RuntimeError('Original driver and audit must finish before supplement')
    frozen=json.loads(previous.with_name(previous.name+'-freeze.json').read_text())
    for source, expected in frozen['source_sha256'].items():
        with Path(source).open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected:
                raise RuntimeError(f'Original candidate source drift: {source}')
    prior=json.loads(PROTOCOL.read_text())['prior_attempt']
    if (Path(prior['path'])/'result.json').exists():
        raise RuntimeError('Supplement is restricted to the unscored attempt')
    if hashlib.sha256(Path(prior['exit_file']).read_bytes()).hexdigest() != prior['exit_sha256']:
        raise RuntimeError('Original interruption record changed')
    path=ROOT/'runs'/f'{TAG}-driver.json'
    if path.exists(): raise RuntimeError('Driver already exists; inspect instead of restarting')
    state=dict(pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat(),phase='launching',tag=TAG)
    write_json(path,state)
    process=subprocess.Popen([sys.executable,'-u',str(ROOT/'scripts/run_generalization_task.py'),
        '--task','make_toast','--tag',TAG,'--protocol',str(PROTOCOL)],cwd=ROOT,start_new_session=True)
    state.update(phase='running',batch_pid=process.pid); write_json(path,state)
    def stop(*_):
        if process.poll() is None: process.terminate()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    code=process.wait(); state.update(phase='auditing',batch_returncode=code); write_json(path,state)
    audit=subprocess.run([sys.executable,str(ROOT/'scripts/audit_make_toast_cells.py'),'--tag',TAG],cwd=ROOT)
    state.update(phase='complete' if code==0 and audit.returncode==0 else 'needs_review',audit_returncode=audit.returncode,ended_at=datetime.now(timezone.utc).isoformat())
    write_json(path,state)


if __name__=='__main__': main()
