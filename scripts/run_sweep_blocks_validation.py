"""Run exactly one registered sweep batch after its prerequisite batches close."""
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


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def preflight(protocol):
    config = protocol['tasks'][0]
    assert len(protocol['tasks']) == 1 and config['task'] == 'sweep_blocks'
    assert config['native_step_limits'] == {'standard':1000, 'random':1000}
    cases = read(ROOT/config['cases_file'])
    assert len(cases) == config['case_count'] == protocol['planned_native_attempts']
    assert len({(c['seed'],c['variant'],c['layout']) for c in cases}) == len(cases)
    for gate in protocol['required_closed_batches']:
        assert digest(gate['closure']) == gate['closure_sha256']
        closed = read(gate['closure'])
        assert closed['complete'] and not closed['live_related_processes']
        assert closed['candidate_commit'] == gate['candidate_commit']
        assert closed['counts']['attempts_closed'] == gate['attempts_closed']
        for row in closed['rows']:
            if row['native_result']:
                assert digest(row['native_result']) == row['native_sha256']
        freeze = read(gate['freeze'])
        for path, sha in freeze['source_sha256'].items():
            assert digest(path) == sha, path
    for name in ['static', 'interfaces']:
        path = ROOT/protocol['verification'][name]
        assert digest(path) == protocol['verification'][name+'_sha256']
        report = read(path)
        assert report['passed']
        for source, sha in report.get('source_sha256', {}).items():
            assert digest(source) == sha, source
    bank = read(ROOT/config['preflight_file'])
    assert bank['passed'] and bank['task'] == 'sweep_blocks'
    assert Path(bank['bank']).resolve() == (ROOT/config['bank']).resolve()
    for path, sha in {**bank['metadata_sha256'],**bank['source_sha256']}.items():
        assert digest(path) == sha, path
    for case in cases:
        suffix = '_random' if case['variant'] == 'random' else ''
        read(ROOT/'data/Assets/Eval_Layout/RoboDojo/arx_x5'/str(case['seed'])/f'sweep_blocks{suffix}_{case["layout"]}.json')
    return dict(case_count=len(cases), original_train_demonstrations=len(bank['demonstrations']),
                original_train_phases=bank['phases'], image_references_verified=bank['images'])


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
        print(json.dumps(checked))
        return
    path = ROOT/'runs'/f'{args.tag}-driver.json'
    assert not any(p.exists() for p in [path,ROOT/'runs'/args.tag,ROOT/'runs'/f'{args.tag}-freeze.json',ROOT/'results'/f'{args.tag}.json']), 'Attempt already exists'
    free = subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True)
    assert int(free.splitlines()[0]) >= protocol['resource_policy']['minimum_free_gpu_mib']
    state = dict(pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(), phase='launching', tag=args.tag,
                 boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 start_ticks=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]), preflight=checked)
    write_json(path,state)
    process = subprocess.Popen([sys.executable,'-u',str(ROOT/'scripts/run_generalization_task.py'),
                                '--task','sweep_blocks','--tag',args.tag,'--protocol',str(protocol_path)],cwd=ROOT,start_new_session=True)
    state.update(phase='running',batch_pid=process.pid)
    write_json(path,state)
    def stop(*_):
        if process.poll() is None:
            process.terminate()
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    code = process.wait()
    state.update(phase='auditing',batch_returncode=code)
    write_json(path,state)
    output = ROOT/'results'/f'{args.tag}.json'
    audit = subprocess.run([sys.executable,str(ROOT/'scripts/audit_sweep_blocks_results.py'),
                            '--tag',args.tag,'--protocol',str(protocol_path),'--output',str(output)],cwd=ROOT)
    report = read(output) if output.exists() else {}
    complete = (code == 0 and audit.returncode == 0 and report.get('complete') and report.get('audit',{}).get('passed')
                and report.get('counts',{}).get('attempts_closed') == protocol['planned_native_attempts'])
    state.update(phase='complete' if complete else 'needs_review',audit_returncode=audit.returncode,
                 report=str(output),counts=report.get('counts'),ended_at=datetime.now(timezone.utc).isoformat())
    write_json(path,state)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
