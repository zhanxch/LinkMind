"""Local task/episode service. No robot dependencies are needed to browse experience."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import uuid

from roborag.episode_files import write_json
from .external_agent import process_identity

ROOT = Path(__file__).resolve().parents[3]
ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
TITLES = dict(fold_clothes="叠衣服", stack_blocks="叠积木", stack_bowls="叠碗", push_T="推齐 T 形块",
              make_toast="制作吐司", hang_mugs="挂杯子", sweep_blocks="清扫积木", pack_objects_into_box="物品装箱",
              pour_liquid_into_cup="倒水", arrange_largest_number="排列数字", sort_nesting_dolls_by_size="套娃排序",
              store_laptop_and_headphones="收纳电脑与耳机")


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid identifier")
    return value


def text_field(data, key, limit=4000, required=False):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"Invalid {key}")
    return value.strip()


class Studio:
    def __init__(self, root=ROOT, state=None):
        self.root = Path(root)
        self.state = Path(state or self.root / "studio/.state")
        self.state.mkdir(parents=True, exist_ok=True)
        self.lease = (self.state / "service.lock").open("w")
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lease.close()
            raise
        (self.state / "tasks").mkdir(exist_ok=True)
        (self.state / "runs").mkdir(exist_ok=True)
        self.manifest = read(self.root / "resources/task-bundles.json")["tasks"]
        self.lock = threading.RLock()
        self.call_lock = threading.Lock()
        self.active = None
        self.process = None
        self.log = None
        from .codex_agent import login_status
        self.codex = login_status()
        # A crashed service's runner has an owner watchdog. Do not claim that
        # physical control is free until its recorded process has actually gone.
        self.orphans = []
        for p in (self.state / "runs").glob("*/studio-run.json"):
            run = read(p)
            if run["status"] in ("starting", "ready", "stopping", "finishing"):
                if process_identity(run.get("pid", 0)) == run.get("pid_identity") and run.get("pid_identity"):
                    self.orphans.append(run)
                run.update(status="interrupted", ended_at=now(), error="Studio restarted; execution was interrupted.")
                write_json(p, run)

    def close(self):
        if self.active:
            self.stop(self.active)
        self.lease.close()

    def tasks(self):
        return sorted((read(p) for p in (self.state / "tasks").glob("*.json")), key=lambda x:x["created_at"], reverse=True)

    def task(self, task_id):
        value = read(self.state / "tasks" / (identifier(task_id) + ".json"))
        if value is None:
            raise ValueError("Task does not exist")
        return value

    def create_task(self, data):
        name = data.get("task")
        if name not in self.manifest:
            raise ValueError("Unknown task")
        profile = data.get("profile", "baseline")
        if profile not in ("baseline", "none") or (profile == "none" and name != "push_T"):
            raise ValueError("Minimal support is currently available for Push-T only")
        variant = data.get("variant", "standard")
        if variant not in ("standard", "random"):
            raise ValueError("Unknown scene variant")
        layout, seed = data.get("layout", 0), data.get("seed", 1)
        if type(layout) is not int or not 0 <= layout <= 24 or type(seed) is not int or not 0 <= seed <= 100000:
            raise ValueError("Invalid scene seed/layout")
        task = dict(id=uuid.uuid4().hex[:16], task=name, title=text_field(data, "title", 120) or TITLES[name],
                    goal=text_field(data, "goal", required=True), constraints=text_field(data, "constraints"),
                    profile=profile, variant=variant, layout=layout, seed=seed, created_at=now(), corrections=[])
        with self.lock:
            write_json(self.state / "tasks" / (task["id"] + ".json"), task)
        return task

    def correction(self, task_id, data):
        note = text_field(data, "text", required=True)
        run_id = data.get("run_id")
        with self.lock:
            task = self.task(task_id)
            if run_id and self.run(run_id)["task_id"] != task_id:
                raise ValueError("Correction source belongs to a different task")
            entry = dict(id=uuid.uuid4().hex[:16], text=note, run_id=run_id, created_at=now(),
                         kind="user_correction", validation="unverified")
            task["corrections"].append(entry)
            write_json(self.state / "tasks" / (task_id + ".json"), task)
        return entry

    def bind_session(self, task_id, session_id):
        """Host-attributed conversation identity; never inferred from model text."""
        identifier(session_id)
        with self.lock:
            task = self.task(task_id)
            if task.get("session_id") not in (None, session_id):
                raise ValueError("Task belongs to a different conversation")
            task["session_id"] = session_id
            write_json(self.state / "tasks" / (task_id + ".json"), task)
        return task

    def check_session(self, session_id, task_id=None, run_id=None):
        identifier(session_id)
        if run_id:
            task_id = self.run(run_id)["task_id"]
        task = self.task(task_id)
        if task.get("session_id") != session_id:
            raise ValueError("This conversation does not own that task. Create a new task here.")
        return {"allowed": True}

    def preflight(self, task=None):
        runtime = read(self.root / "local.runtime.json", {})
        checks = {"运行配置": bool(runtime), "仿真解释器": Path(runtime.get("sim_python", "/missing")).is_file(),
                  "策略解释器": Path(runtime.get("policy_python", "/missing")).is_file(),
                  "仿真资产": (self.root / "data/Assets").is_dir(),
                  "HexaShell": (self.root / "vendor/HexaShell").is_dir(),
                  "MCP 依赖": (self.root / ".runtime/mcp/mcp").is_dir()}
        if task:
            entry = self.manifest[task["task"]]
            checks["经验库"] = (self.root / entry["install"] / "execution-index.json").is_file()
            checks["TRAIN 文件"] = all((self.root / "data" / item["path"]).is_file() for item in entry["train"])
            simtask = task["task"] + ("_random" if task["variant"] == "random" else "")
            checks["场景布局"] = (self.root / f"data/Assets/Eval_Layout/RoboDojo/arx_x5/{task['seed']}/{simtask}_{task['layout']}.json").is_file()
        return {"ready": all(checks.values()), "checks": checks,
                "note": "Path checks only; native startup validates actual runtime compatibility."}

    def run(self, run_id):
        record = read(self.state / "runs" / identifier(run_id) / "studio-run.json")
        if record is None:
            raise ValueError("Run does not exist")
        return record

    def output(self, run_id):
        return self.state / "runs" / identifier(run_id) / "episode"

    def update(self, run_id, **fields):
        run = self.run(run_id)
        run.update(fields)
        write_json(self.state / "runs" / run_id / "studio-run.json", run)
        return run

    def refresh(self):
        with self.lock:
            if not self.active:
                return
            run_id = self.active
            run, output = self.run(run_id), self.output(run_id)
            code = self.process.poll()
            if code is not None:
                result = read(output / "result.json")
                state = "stopped" if run["status"] == "stopping" else ("completed" if code == 0 and result else "failed")
                error = read(output / "exit.json", {}).get("detail")
                self.update(run_id, status=state, returncode=code, ended_at=now(), result=result, error=error)
                self.active = self.process = None
                self.log.close()
                self.log = None
            elif run["status"] == "starting" and (output / "studio-agent.json").is_file():
                self.update(run_id, status="ready")

    def start(self, task_id):
        with self.lock:
            self.refresh()
            if self.active or any(process_identity(r["pid"]) == r["pid_identity"] for r in self.orphans):
                raise ValueError("The simulator is occupied; wait for the current process to end")
            task = self.task(task_id)
            check = self.preflight(task)
            if not check["ready"]:
                raise ValueError("Missing setup: " + ", ".join(k for k,v in check["checks"].items() if not v))
            run_id = uuid.uuid4().hex[:16]
            directory = self.state / "runs" / run_id
            directory.mkdir()
            runtime = read(self.root / "local.runtime.json")
            args = [runtime["policy_python"], str(self.root / "scripts/run_task.py"), "--task", task["task"],
                    "--variant", task["variant"], "--layout", str(task["layout"]), "--seed", str(task["seed"]),
                    "--controller", "delta", "--push-simplification", task["profile"],
                    "--agent-backend", "dsh", "--model", "dsh-session-see-transcript",
                    "--studio-owner-pid", str(os.getpid()), "--studio-owner-identity", process_identity(os.getpid()),
                    "--output", str(directory / "episode")]
            run = dict(id=run_id, task_id=task_id, task=task["task"], profile=task["profile"], created_at=now(),
                       status="starting", task_snapshot=task, result=None, control_fault=None)
            write_json(directory / "studio-run.json", run)
            self.log = (directory / "runner.log").open("w")
            try:
                self.process = subprocess.Popen(args, cwd=self.root, stdout=self.log, stderr=subprocess.STDOUT,
                                                start_new_session=True)
            except Exception:
                self.log.close()
                self.log = None
                self.update(run_id, status="failed", error="Failed to start runner", ended_at=now())
                raise
            self.active = run_id
            return self.update(run_id, pid=self.process.pid, pid_identity=process_identity(self.process.pid))

    def stop(self, run_id):
        with self.lock:
            self.refresh()
            if self.active != run_id:
                return self.run(run_id)
            self.update(run_id, status="stopping")
            process = self.process
            # Runner's SIGTERM handler cleans up its separately grouped MCP and
            # simulator children. Do not mark stopped until wait() confirms it.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=35)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Stop is still pending; execution ownership has not been released")
        self.refresh()
        return self.run(run_id)

    def require_active(self, run_id):
        self.refresh()
        run = self.run(run_id)
        if run_id != self.active or run["status"] != "ready":
            raise ValueError("This run is not ready/active. Never redirect an old session to a different run.")
        return run

    def finish(self, run_id, controller="ui"):
        with self.lock:
            self.require_active(run_id)
            write_json(self.output(run_id) / "studio-finish.json", {"requested_at": now()})
            return self.update(run_id, status="finishing")

    def native_request(self, run_id, method, params=None):
        endpoint = read(self.output(run_id) / "studio-agent.json")["mcp_url"]
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        def send(payload):
            with urlopen(Request(endpoint, json.dumps(payload).encode(), headers), timeout=550) as response:
                if response.headers.get("Mcp-Session-Id"):
                    headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
                body = response.read()
                return json.loads(body) if body else {}
        handshake = send(dict(jsonrpc="2.0", id=1, method="initialize", params={
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "linkmind-studio", "version": "0.1.0"}}))
        if "error" in handshake:
            raise RuntimeError("Native MCP initialization failed")
        headers["MCP-Protocol-Version"] = handshake["result"]["protocolVersion"]
        send(dict(jsonrpc="2.0", method="notifications/initialized"))
        try:
            reply = send(dict(jsonrpc="2.0", id=2, method=method, params=params or {}))
            if "error" in reply:
                raise RuntimeError(str(reply["error"]))
            return reply["result"]
        finally:
            if "Mcp-Session-Id" in headers:
                try:
                    with urlopen(Request(endpoint, headers=headers, method="DELETE"), timeout=3):
                        pass
                except Exception:
                    pass  # Session expiry does not authorize retrying the call.

    def tools(self, run_id):
        self.require_active(run_id)
        return self.native_request(run_id, "tools/list")

    def call(self, run_id, data, controller="dsh"):
        call_id = identifier(data.get("call_id"))
        tool = identifier(data.get("tool"))
        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be an object")
        if not self.call_lock.acquire(blocking=False):
            raise ValueError("A robot call is already in flight; do not retry motion")
        try:
            run = self.require_active(run_id)
            directory = self.state / "runs" / run_id / "bridge"
            directory.mkdir(exist_ok=True)
            path = directory / (call_id + ".json")
            fingerprint = hashlib.sha256(json.dumps([tool, arguments], sort_keys=True).encode()).hexdigest()
            old = read(path)
            if old:
                if old["fingerprint"] != fingerprint:
                    raise ValueError("call_id was already used with different arguments")
                if "result" in old:
                    return old["result"]
                raise ValueError("This call has an unknown outcome. Do not replay it; stop the run.")
            if run["control_fault"] and tool != "observe":
                raise ValueError("A previous call has an unknown outcome. Observe or stop; motion is blocked.")
            # Validate against the current episode's advertised native surface.
            available = {t["name"] for t in self.tools(run_id)["tools"]}
            if tool not in available:
                raise ValueError("Tool is not available under this episode's support profile")
            record = dict(call_id=call_id, tool=tool, arguments=arguments, fingerprint=fingerprint, started_at=now())
            write_json(path, record)
            try:
                result = self.native_request(run_id, "tools/call", {"name": tool, "arguments": arguments})
            except Exception as exc:
                with self.lock:
                    self.update(run_id, control_fault="Unknown tool outcome; no automatic retry")
                raise RuntimeError("Robot call outcome is unknown; observe or stop this run") from exc
            record.update(result=result, ended_at=now())
            write_json(path, record)
            if result.get("isError"):
                with self.lock:
                    self.update(run_id, control_fault="Native tool reported an error; motion requires a new run")
            return result
        finally:
            self.call_lock.release()

    def context(self, run_id):
        self.refresh()
        run = self.run(run_id)
        task = self.task(run["task_id"])
        agent = read(self.output(run_id) / "studio-agent.json", {})
        return dict(run=run, task=task, episode_instructions=agent.get("prompt"),
                    guidance="Call episode_tools for this exact run_id. Follow native tool schemas and instructions. "
                    "Corrections are user input, not verified successful experience. Native score judges the benchmark goal only.")

    def experience(self, task, experience_id=None):
        entry = self.manifest[task]
        bank = self.root / entry["bundle"]
        graphs = read(bank / "bank.json")["graphs"]
        items = []
        for g in graphs:
            if g.get("task") != task or (experience_id and g["id"] != experience_id):
                continue
            path = bank / "graphs" / (identifier(g["id"]) + ".json")
            graph = read(path)
            items.append({**g, "source": graph["source"], "semantics": graph.get("semantics"),
                          "metadata_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "phases": [n for n in graph["nodes"] if n["kind"] == "phase"]})
        if experience_id and not items:
            raise ValueError("Experience does not exist for this task")
        return items

    def snapshot(self):
        self.refresh()
        tasks = self.tasks()
        runs = []
        for p in (self.state / "runs").glob("*/studio-run.json"):
            run = read(p)
            output = self.output(run["id"])
            run["observation"] = read(output / "obs/state.json")
            run["progress"] = read(output / "progress.json")
            runs.append(run)
        return dict(tasks=tasks, runs=sorted(runs, key=lambda r:r["created_at"], reverse=True), active=self.active,
                    catalog=[dict(id=k, title=TITLES[k], profiles=["baseline", "none"] if k=="push_T" else ["baseline"])
                             for k in self.manifest], preflight=self.preflight(),
                    historical=read(self.root / "results/local-summary.json"), codex=self.codex)

    def live_run(self, run_id):
        """Read only published observations and the real final report, never simulator internals."""
        self.refresh()
        run = self.run(run_id)
        output = self.output(run_id)
        observation = read(output / "obs/state.json", {})
        progress = read(output / "progress.json", {})
        camera = read(output / "live/frame.json")
        return {**run, "step": (camera or {}).get("step", observation.get("step", progress.get("step"))),
                "observation_available": bool(observation),
                "camera": camera,
                "camera_error": read(output / "live/error.json")}

    def asset(self, run_id, name):
        output = self.output(run_id)
        allowed = {f"{c}.png": output / f"obs/{c}.png" for c in ("head", "wrist_l", "wrist_r")}
        for camera in ("head", "wrist_l", "wrist_r"):
            live = output / "live" / f"{camera}.png"
            if live.is_file():
                allowed[f"{camera}.png"] = live
        allowed.update({"result.json": output / "result.json", "run.json": output / "run.json",
                        "commands.jsonl": output / "commands.jsonl", "runner.log": output.parent / "runner.log",
                        "codex-events.jsonl": output.parent / "codex-events.jsonl", "codex-answer.txt": output.parent / "codex-answer.txt"})
        if name not in allowed or not allowed[name].is_file():
            raise ValueError("Artifact is not available")
        return allowed[name]


def serve(studio, port, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, value, content_type="application/json"):
            body = json.dumps(value, ensure_ascii=False).encode() if content_type == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def stream_run(self, run_id):
            # Each connection begins with a full snapshot, so reconnect/replay cannot
            # lose the final score. No model call or robot command is made here.
            value = studio.live_run(run_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            previous = None
            try:
                for tick in range(480):  # reconnect periodically; no abandoned infinite worker
                    payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if payload != previous:
                        self.wfile.write(("data: " + payload + "\n\n").encode())
                        previous = payload
                    elif tick % 20 == 0:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    if value["status"] not in ("starting", "ready", "finishing", "stopping"):
                        return
                    time.sleep(0.25)
                    value = studio.live_run(run_id)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def handle_request(self):
            if not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.respond(401, {"error": "Unauthorized"})
                return
            try:
                path = urlsplit(self.path).path
                parts = path.strip("/").split("/")
                data = {}
                if self.command == "POST":
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1024*1024:
                        raise ValueError("Request body must be 1–1048576 bytes")
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError("Expected a JSON object")
                if self.command == "GET" and path == "/api/state":
                    value = studio.snapshot()
                elif self.command == "GET" and len(parts) in (3, 4) and parts[:2] == ["api", "experience"]:
                    value = studio.experience(parts[2], parts[3] if len(parts) == 4 else None)
                elif self.command == "POST" and path == "/api/session/check":
                    value = studio.check_session(data["session_id"], data.get("task_id"), data.get("run_id"))
                elif self.command == "POST" and path == "/api/tasks":
                    value = studio.create_task(data)
                elif self.command == "POST" and len(parts) == 4 and parts[:2] == ["api", "tasks"]:
                    if parts[3] == "start": value = studio.start(parts[2])
                    elif parts[3] == "bind-session": value = studio.bind_session(parts[2], data["session_id"])
                    elif parts[3] == "corrections": value = studio.correction(parts[2], data)
                    else: raise ValueError("Unknown action")
                elif len(parts) == 4 and parts[:2] == ["api", "runs"]:
                    run_id, action = parts[2:]
                    if self.command == "GET" and action == "stream":
                        self.stream_run(run_id)
                        return
                    elif self.command == "GET" and action == "live": value = studio.live_run(run_id)
                    elif self.command == "GET" and action == "context": value = studio.context(run_id)
                    elif self.command == "GET" and action == "tools": value = studio.tools(run_id)
                    elif self.command == "POST" and action == "call": value = studio.call(run_id, data, self.headers.get("X-LinkMind-Controller", "ui"))
                    elif self.command == "POST" and action == "stop": value = studio.stop(run_id)
                    elif self.command == "POST" and action == "finish": value = studio.finish(run_id, self.headers.get("X-LinkMind-Controller", "ui"))
                    else: raise ValueError("Unknown action")
                elif self.command == "GET" and len(parts)==5 and parts[:2]==["api", "runs"] and parts[3]=="artifacts":
                    file = studio.asset(parts[2], parts[4])
                    self.respond(200, file.read_bytes(), mimetypes.guess_type(str(file))[0] or "text/plain")
                    return
                else:
                    self.respond(404, {"error": "Not found"})
                    return
                self.respond(200, value)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self.respond(400, {"error": str(exc)})
            except Exception as exc:
                self.respond(500, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    studio.service_url = f"http://127.0.0.1:{server.server_port}"
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--owner-pid", type=int)
    parser.add_argument("--owner-identity")
    args = parser.parse_args()
    token = os.environ["LINKMIND_STUDIO_TOKEN"]
    studio = Studio(state=args.state)
    server = serve(studio, args.port, token)
    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    if args.owner_pid:
        from .external_agent import watch_owner
        watch_owner(args.owner_pid, args.owner_identity)
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}"}), flush=True)
    try:
        server.serve_forever()
    finally:
        studio.close()
        server.server_close()


if __name__ == "__main__":
    main()
