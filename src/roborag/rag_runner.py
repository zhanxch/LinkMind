#!/usr/bin/env python3
"""One native robot episode: MCP evidence -> GPT plan -> GPT action chunks."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from .hexashell_agent import run_agent
from .episode_files import write_json as save, read_jsonl
from .episode_budget import add_budget_argument, budget_arguments
from .rag_accounting import control_accounting, workflow_completed
from .rag_tasks import TASKS, prompt_for, simulation_task
from .sop_store import default_bank, evidence_source_paths, sop_prompt


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wait_file(path, process, seconds=300):
    started = time.monotonic()
    while not path.exists():
        if process.poll() is not None:
            raise RuntimeError(f"Process exited {process.returncode} before {path}")
        if time.monotonic()-started > seconds:
            raise TimeoutError(str(path))
        time.sleep(.2)


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", choices=sorted(TASKS), default="stack_blocks")
    parser.add_argument("--variant", choices=["standard", "random"], default="standard")
    parser.add_argument("--bank", type=Path, help="Full TRAIN evidence bank for the selected task")
    parser.add_argument("--layout", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--agent-backend", choices=["cli", "dsh"], default="cli")
    parser.add_argument("--studio-owner-pid", type=int)
    parser.add_argument("--studio-owner-identity")
    parser.add_argument("--max-wall-seconds", type=float, default=5400)
    add_budget_argument(parser)
    parser.add_argument("--no-rag", action="store_true")
    parser.add_argument("--controller", choices=["tcp", "delta"], default="delta")
    from .push_simplification import PROFILES, validate_profile, prompt_for_profile, workflow_for_profile, FIXED_PACKAGE
    parser.add_argument("--push-simplification", choices=PROFILES, default="baseline")
    args = parser.parse_args()
    if args.agent_backend == "dsh":
        from .studio.external_agent import watch_owner
        watch_owner(args.studio_owner_pid, args.studio_owner_identity)
    validate_profile(args.push_simplification, args.task, args.controller, args.no_rag)
    if args.bank is None:
        args.bank = default_bank(ROOT, args.task)
        if args.task == "fold_clothes" and not (args.bank / "execution-index.json").exists():
            parser.error("Restore the full v3 evidence with scripts/restore_v3_evidence.py first")
    task = simulation_task(args.task, args.variant)
    prompt = prompt_for(ROOT, args.task, args.controller, no_rag=args.no_rag)
    if (args.bank / "manifest.json").exists():
        prompt = sop_prompt(prompt)
    prompt = prompt_for_profile(prompt, args.push_simplification)
    runtime = json.loads((ROOT / "local.runtime.json").read_text())
    sys.path.insert(0, runtime["upstream"])
    from roboicl.paths import python_paths
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    workspace = Path(tempfile.mkdtemp(prefix="roborag-mcp-"))
    for name in ("bin", "obs", "inbox", "outbox"):
        (workspace / name).mkdir()
    (workspace / "bin/python").symlink_to("/usr/bin/python3")
    save(output / "agent-workspace.json", {"path": str(workspace)})
    hexa = ROOT / "vendor/HexaShell"
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONNOUSERSITE="1", OMNI_KIT_ACCEPT_EULA="YES",
        OMNI_KIT_ALLOW_ROOT="1", CUDA_VISIBLE_DEVICES="0", ROBOICL_DATA_ROOT=str(ROOT / "data"),
        ROBOICL_RESULTS_ROOT=str(output / "native"), ROBODOJO_RUN_ID=output.name, OMP_NUM_THREADS="4",
        PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(hexa), *python_paths("sim")]),
        LD_PRELOAD=str(Path(runtime["sim_library"]) / "libstdc++.so.6"), LD_LIBRARY_PATH=runtime["sim_library"])
    sim_command = [runtime["sim_python"], "-u", "-m", "roborag.rag_sim", "--task", task,
        "--output", str(output), "--agent-workspace", str(workspace), "--hexashell", str(hexa),
        "--layout", str(args.layout), "--seed", str(args.seed), "--max-wall-seconds", str(args.max_wall_seconds),
        "--enable_cameras", "--headless",
        "--kit_args=--enable isaacsim.replicator.behavior --enable isaacsim.sensors.camera --/app/hangDetector/enabled=false --/app/updateOrder/checkForHydraRenderComplete=1000 --/app/renderer/waitIdle=true --/app/hydraEngine/waitIdle=true"]
    sim_command += budget_arguments(args.control_step_limit)
    if args.agent_backend == "dsh":
        sim_command += ["--live-camera-fps", "4"]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    mcp_env = dict(os.environ, PYTHONPATH=str(ROOT / ".runtime/mcp") + os.pathsep + str(ROOT / "src"))
    mcp_command = [runtime["policy_python"], "-m", "roborag.rag_mcp", "--bank", str(args.bank.resolve()),
        "--data", str(ROOT / "data"), "--workspace", str(workspace), "--output", str(output),
        "--port", str(port), "--controller", args.controller, "--task", args.task] + (["--no-rag"] if args.no_rag else [])
    if args.push_simplification != "baseline":
        mcp_command += ["--push-simplification", args.push_simplification]
    paths = [ROOT / "src/roborag" / name for name in ("rag_mcp.py", "rag_execution.py", "rag_sim.py",
        "hexashell_adapter.py", "hexashell_agent.py", "graph_retrieval.py", "graph_chunks.py",
        "rag_tasks.py", "rag_accounting.py", "episode_files.py", "scene_measurements.py", "action_targets.py", "sop_store.py", "toast_motion.py")]
    paths += sorted((ROOT / "src/roborag/mcp").glob("*.py"))
    paths += [ROOT / "src/roborag" / name for name in ("episode_budget.py", "scene_registration.py", "scene_transfer.py")]
    paths += [Path(__file__).resolve(), *evidence_source_paths(args.bank.resolve())]
    paths += [ROOT / "src/roborag/push_simplification.py"]
    if args.agent_backend == "dsh":
        paths += sorted((ROOT / "src/roborag/studio").glob("*.py"))
        paths += [ROOT / "studio/package-lock.json", ROOT / "studio/launch.mjs", ROOT / "studio/preset.mjs"]
        paths += sorted((ROOT / "studio/plugin").glob("*.*"))
    if args.push_simplification == "fixed":
        paths += [FIXED_PACKAGE]
    paths += sorted((hexa / "tasks/fold_clothes/tools/cloth_view").glob("*.py"))
    paths += [hexa / "tools/table_plane/tool.py"]
    if args.task == "hang_mugs":
        paths += [ROOT / "src/roborag/hang_measurements.py"]
        paths += [hexa / f"tasks/hang_mugs/tools/{name}/tool.py" for name in ("precision", "pegs")]
    if args.task == "push_T":
        paths += [ROOT / "src/roborag" / name for name in
                  ("reference_context.py", "planar_mcp.py", "planar_measurements.py")]
        paths += [hexa / "tasks/push_T/tools/planar_contact/tool.py"]
        native_client = Path(runtime["upstream"]) / "third_party/RoboDojo/src/eval_client"
        paths += [native_client / name for name in ("ik_continuity.py", "eval_env.py")]
    save(output / "run.json", dict(started_at=datetime.now(timezone.utc).isoformat(),
        args={k:str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
        schema="roborag.mcp-pilot.v2", task=task, model=args.model,
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        source_sha256={str(p):digest(p) for p in paths},
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        layout_sha256=digest(ROOT / f"data/Assets/Eval_Layout/RoboDojo/arx_x5/{args.seed}/{task}_{args.layout}.json"),
        observation="current RGB + camera calibration + robot proprioception; no object ground truth",
        execution_guard=({"kind": "native_ik_continuity", "max_joint_increment_rad": .25}
                         if args.task in ("push_T", "make_toast", "hang_mugs", "sweep_blocks", "pack_objects_into_box") else None),
        controller=("RoboICL world link6 delta grammar; native RoboDojo EE control" if args.controller == "delta"
                    else "HexaShell kinematic adapter; GPT authored TCP waypoint chunks"),
        workflow=("MCP retrieval -> GPT new plan -> GPT chunks -> native evaluator" if args.push_simplification == "baseline"
                  else "Push_T cumulative simplification: " + args.push_simplification)))
    processes, started = [], time.monotonic()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        with (output / "simulator.log").open("w") as log:
            sim = subprocess.Popen(sim_command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(sim)
        save(output / "process.json", dict(simulator_pid=sim.pid, runner_pid=os.getpid()))
        wait_file(output / "ready.json", sim)
        ready = json.loads((output / "ready.json").read_text())
        if args.control_step_limit is not None and ready["step_limit"] != args.control_step_limit:
            raise RuntimeError("Simulator did not apply the requested control step limit")
        with (output / "mcp-server.log").open("w") as log:
            mcp = subprocess.Popen(mcp_command, cwd=ROOT, env=mcp_env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(mcp)
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.1):
                    break
            except OSError:
                if mcp.poll() is not None:
                    raise RuntimeError("MCP server exited")
                time.sleep(.1)
        else:
            raise TimeoutError("MCP server startup")
        if args.agent_backend == "dsh":
            from .studio.external_agent import wait_for_external_agent
            agent = wait_for_external_agent(workspace, output, prompt, f"http://127.0.0.1:{port}/mcp", sim,
                args.max_wall_seconds-(time.monotonic()-started))
        else:
            agent = run_agent(workspace, output, prompt, model=args.model, effort=args.effort,
                timeout=args.max_wall_seconds-(time.monotonic()-started),
                python_packages=ROOT / "data/hexashell-agent-python", mcp_url=f"http://127.0.0.1:{port}/mcp")
        if not json.loads((workspace / "obs/state.json").read_text())["episode_over"]:
            save(workspace / "inbox/99999999999999999999-agent-exit.json", {"finish": "agent_exit"})
        if sim.wait(timeout=120):
            raise RuntimeError("Simulator finalization failed")
        completed = json.loads((output / "sim_complete.json").read_text())
        native = json.loads(Path(completed["native_result"]).read_text())
        if native.get("eval_time") != 1 or native.get("policy_error"):
            raise RuntimeError("Incomplete native evaluation")
        calls, malformed_calls = read_jsonl(output / "mcp-calls.jsonl")
        names = [c["tool"] for c in calls]
        result = dict(complete=True, native=native, native_result=completed["native_result"],
            budget={key: ready[key] for key in ("native_step_limit", "control_step_limit_override", "step_limit", "budget_mode")},
            native_sha256=digest(completed["native_result"]), native_agent=agent,
            wall_seconds=time.monotonic()-started, actual_billed_usd=None,
            retrieval_before_plan_before_execution=workflow_completed(calls),
            profile_workflow_verified=workflow_for_profile(calls, args.push_simplification),
            **control_accounting(output, calls), malformed_mcp_records=malformed_calls,
            tool_counts={name:names.count(name) for name in sorted(set(names))},
            caveat="One development episode; no causal retrieval benefit or heldout success rate established.")
        save(output / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except BaseException as exc:
        save(output / "exit.json", dict(complete=False, error=type(exc).__name__, detail=str(exc), wall_seconds=time.monotonic()-started))
        raise
    finally:
        for process in reversed(processes):
            stop(process)


if __name__ == "__main__":
    main()
