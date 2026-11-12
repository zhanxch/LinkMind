"""Let a separate dsh session drive the existing episode MCP server."""
import json
import os
from pathlib import Path
import signal
import threading
import time

from roborag.episode_files import write_json


def process_identity(pid):
    try:
        # starttime survives PID reuse; comm can contain spaces/parentheses.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def watch_owner(pid, identity):
    if not pid or not identity or process_identity(pid) != identity:
        raise RuntimeError("Studio owner is unavailable")
    def watch():
        while process_identity(pid) == identity:
            time.sleep(1)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=watch, daemon=True).start()


def wait_for_external_agent(workspace, output, prompt, mcp_url, simulator, timeout):
    started = time.monotonic()
    write_json(output / "studio-agent.json", {
        "schema": "linkmind.dsh-episode.v1", "mcp_url": mcp_url,
        "prompt": prompt, "backend": "dsh", "workspace": str(workspace),
    })
    while True:
        if (output / "studio-finish.json").exists():
            break
        state = json.loads((workspace / "obs/state.json").read_text())
        if state["episode_over"]:
            break
        if simulator.poll() is not None:
            raise RuntimeError("Simulator ended before the Studio episode was finalized")
        if time.monotonic() - started >= timeout:
            raise TimeoutError("Studio episode exceeded its wall-time budget")
        time.sleep(.2)
    result = {"backend": "dsh", "returncode": 0, "wall_seconds": time.monotonic() - started,
              "accounting": {}, "note": "Model transcript and selected provider/model route belong to the dsh session."}
    write_json(output / "agent-exit.json", result)
    return result
