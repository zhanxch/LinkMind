#!/usr/bin/env python3
"""Run the registered first pass once, then verify its native evidence."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from roborag.episode_files import write_json

TAG = "push-t-toolkit-v1-dev-20261103"
PROTOCOL = ROOT / "experiments/push_T/toolkit-v1-development-20261103.json"


def main():
    path = ROOT / "runs" / f"{TAG}-driver.json"
    if path.exists():
        raise RuntimeError("This driver already exists; inspect it instead of restarting")
    state = dict(pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(),
                 phase="launching", tag=TAG)
    write_json(path, state)
    command = [sys.executable, "-u", str(ROOT / "scripts/run_generalization_task.py"),
               "--task", "push_T", "--tag", TAG, "--protocol", str(PROTOCOL)]
    process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
    state.update(phase="running", batch_pid=process.pid)
    write_json(path, state)

    def stop(signum, frame):
        if process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    code = process.wait()
    state.update(batch_returncode=code, phase="auditing")
    write_json(path, state)
    report = ROOT / "results/push-t-toolkit-v1-dev-20261103.json"
    audit = subprocess.run([sys.executable, str(ROOT / "scripts/audit_push_t_current.py"),
                            "--tag", TAG, "--output", str(report), "--protocol", str(PROTOCOL)], cwd=ROOT)
    summary = json.loads(report.read_text()) if report.exists() else {}
    state.update(phase="complete" if code == 0 and audit.returncode == 0 and summary.get("complete") else "needs_review",
                 audit_returncode=audit.returncode, report=str(report),
                 counts=summary.get("counts"), ended_at=datetime.now(timezone.utc).isoformat())
    write_json(path, state)
    if state["phase"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
