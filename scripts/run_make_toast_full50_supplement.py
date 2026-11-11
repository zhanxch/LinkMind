#!/usr/bin/env python3
"""Run only the explicitly authorized unscored full50 scenes once each."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from roborag.episode_files import write_json

TAG = "make-toast-python-cells-full50-supplement-20261105"
BASE = "b4ace31f1a0b0549db64cc9775be23280628accf"
PROTOCOL = ROOT / "experiments/make_toast/full50-unscored-supplement-20261105.json"


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def preflight():
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["base_commit"] == BASE
    parent = protocol["parent_batch"]
    for name in ("report", "closure", "freeze"):
        assert digest(parent[name]) == parent[name + "_sha256"]
    report = json.loads(Path(parent["report"]).read_text())
    closure = json.loads(Path(parent["closure"]).read_text())
    freeze = json.loads(Path(parent["freeze"]).read_text())
    status = json.loads((ROOT / "runs" / parent["tag"] / "status.json").read_text())
    assert status["complete"] and not status["active"] and not status["pending"]
    assert report["complete"] and report["audit"]["passed"] and closure["complete"]
    assert report["candidate_commit"] == freeze["candidate_commit"] == BASE
    assert protocol["conditions"] == freeze["conditions"]
    assert closure["live_related_processes"] == []
    expected = [{k: r[k] for k in ("seed", "variant", "layout")}
                for r in report["cases"] if r["success"] is None]
    cases = json.loads((ROOT / protocol["tasks"][0]["cases_file"]).read_text())
    assert cases == expected and len(cases) == protocol["planned_native_attempts"] == 3
    assert protocol["tasks"][0]["case_count"] == len(cases)
    for row in parent["unscored"]:
        path = Path(row["directory"])
        assert not (path / "result.json").exists()
        assert not list((path / "native").rglob("_result.json"))
        for artifact, sha in row["artifact_sha256"].items():
            assert digest(artifact) == sha, artifact
    for source, sha in freeze["source_sha256"].items():
        assert digest(source) == sha, source
    subprocess.run(["git", "diff", "--exit-code", BASE, "--", "src", "prompts"],
                   cwd=ROOT, check=True)
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "src", "prompts"],
        cwd=ROOT, text=True)
    assert not dirty, "Runtime must match the original full50 candidate"


def main():
    preflight()
    path = ROOT / "runs" / f"{TAG}-driver.json"
    if any(p.exists() for p in (path, ROOT / "runs" / TAG,
                               ROOT / "runs" / f"{TAG}-freeze.json")):
        raise RuntimeError("This supplement already exists; inspect it instead of restarting")
    state = dict(pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat(),
                 phase="launching", tag=TAG, original_full50_commit=BASE)
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
        [sys.executable, str(ROOT / "scripts/audit_make_toast_results.py"),
         "--tag", TAG, "--protocol", str(PROTOCOL), "--output", str(report)], cwd=ROOT)
    summary = json.loads(report.read_text()) if report.exists() else {}
    complete = (code == 0 and audit.returncode == 0 and summary.get("complete")
                and summary.get("audit", {}).get("passed")
                and summary.get("counts", {}).get("attempts_closed") == 3)
    state.update(phase="complete" if complete else "needs_review",
                 audit_returncode=audit.returncode, report=str(report),
                 counts=summary.get("counts"), ended_at=datetime.now(timezone.utc).isoformat())
    write_json(path, state)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
