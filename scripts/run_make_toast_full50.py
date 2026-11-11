#!/usr/bin/env python3
"""Run the accepted toast candidate over the full registered set exactly once."""
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

TAG = "make-toast-python-cells-full50-20261104"
BASE = "1fe37046809b3816d4c70a74c41abbe3bff3e243"
PROTOCOL = ROOT / "experiments/make_toast/python-cells-full50-20261104.json"


def preflight():
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["base_commit"] == BASE
    cases = json.loads((ROOT / protocol["tasks"][0]["cases_file"]).read_text())
    expected = [dict(variant=v, layout=l, seed=1)
                for l in range(25) for v in ("standard", "random")]
    assert cases == expected and protocol["tasks"][0]["case_count"] == 50
    for tag in ("make-toast-reliability-v2-dev-20261104",
                "make-toast-reliability-v2-random-supplement-20261104"):
        status = json.loads((ROOT / "runs" / tag / "status.json").read_text())
        driver = json.loads((ROOT / "runs" / f"{tag}-driver.json").read_text())
        assert status["complete"] and not status["active"] and not status["pending"]
        assert driver["phase"] == "complete"
    subprocess.run(["git", "diff", "--exit-code", BASE, "--", "src", "prompts"],
                   cwd=ROOT, check=True)
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "src", "prompts"],
        cwd=ROOT, text=True)
    assert not dirty, "Runtime must match the accepted, committed candidate"


def main():
    preflight()
    path = ROOT / "runs" / f"{TAG}-driver.json"
    if any(p.exists() for p in (path, ROOT / "runs" / TAG,
                               ROOT / "runs" / f"{TAG}-freeze.json")):
        raise RuntimeError("This attempt already exists; inspect it instead of restarting")
    state = dict(pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(),
                 phase="launching", tag=TAG, accepted_runtime_commit=BASE)
    write_json(path, state)
    process = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "scripts/run_generalization_task.py"),
         "--task", "make_toast", "--tag", TAG, "--protocol", str(PROTOCOL)],
        cwd=ROOT, start_new_session=True)
    state.update(phase="running", batch_pid=process.pid)
    write_json(path, state)

    def stop(*_):
        if process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    code = process.wait()
    state.update(phase="auditing", batch_returncode=code)
    write_json(path, state)
    report = ROOT / "results" / f"{TAG}.json"
    audit = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_make_toast_full50.py"),
         "--tag", TAG, "--protocol", str(PROTOCOL), "--output", str(report)], cwd=ROOT)
    summary = json.loads(report.read_text()) if report.exists() else {}
    complete = (code == 0 and audit.returncode == 0 and summary.get("complete")
                and summary.get("audit", {}).get("passed")
                and summary.get("counts", {}).get("attempts_closed") == 50)
    state.update(phase="complete" if complete else "needs_review",
                 audit_returncode=audit.returncode, report=str(report),
                 counts=summary.get("counts"), ended_at=datetime.now(timezone.utc).isoformat())
    write_json(path, state)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
