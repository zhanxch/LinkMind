"""dsh's stdio MCP bridge, with explicit episode identity on every robot call."""
import json
import os
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote
from typing import Annotated
from pydantic import Field

from mcp.server import MCPServer
from mcp.types import CallToolResult, ToolAnnotations
from mcp.server.mcpserver.exceptions import ToolError


def request(path, data=None):
    headers = {"Authorization": "Bearer " + os.environ["LINKMIND_STUDIO_TOKEN"], "Content-Type": "application/json",
               "X-LinkMind-Controller": os.environ.get("LINKMIND_CONTROLLER", "dsh")}
    body = None if data is None else json.dumps(data).encode()
    try:
        with urlopen(Request(os.environ["LINKMIND_STUDIO_URL"] + path, body, headers), timeout=600) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        raise ToolError(json.loads(exc.read()).get("error", "Studio request failed")) from exc


def create_server(*, basic=False):
    server = MCPServer("LinkMind Studio", instructions=(
        "LinkMind runs embodied simulation tasks from the user's conversational goal and constraints. "
        "Use studio_catalog and create_task, then start_episode when the user requested execution. "
        "Operate only the run_id returned by that start. Never select a newer run implicitly. "
        "First read task_context, then episode_tools, then follow the returned native episode instructions and JSON schemas. "
        "robot_call forwards native text AND image content without changing action semantics. "
        "Use a unique call_id for each intended call; reuse that same id only to recover that call's recorded result. "
        "Never repeat motion with a new call_id after a timeout. Stop and report unknown outcomes. "
        "The selected support profile is fixed for each episode. User corrections are unverified input, not measured success. "
        "Use finish_episode when done, then read task_context to inspect the actual native result. "
        "A chat cancellation is not a robot stop: use the Studio Stop button to end execution."))
    readonly = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

    @server.tool(annotations=readonly)
    def studio_catalog() -> dict:
        """List task types, existing tasks/runs, runtime readiness and the active simulation. No execution."""
        state = request('/api/state')
        return {k: state[k] for k in ('catalog', 'tasks', 'runs', 'active', 'preflight')}

    def view_experience(task: str, experience_id: str = '') -> list:
        """Read historical TRAIN evidence: what happened, its source, and uncertainties. Not a skill or mandatory procedure.

        Omit experience_id to browse a task; pass an exact ID to inspect a user-selected reference.
        Judge its applicability against the current scene. Full trajectory retrieval uses native episode tools when available.
        """
        suffix = '/' + quote(experience_id, safe='') if experience_id else ''
        return request(f'/api/experience/{quote(task, safe="")}{suffix}')

    @server.tool()
    def create_task(task: str, goal: str, constraints: str = '', profile: str = 'baseline',
                    variant: str = 'standard', layout: int = 0, seed: int = 1, title: str = '') -> dict:
        """Save the user's goal and constraints as a task. Does not start execution. Push-T also supports profile none."""
        return request('/api/tasks', dict(task=task, goal=goal, constraints=constraints, profile=profile,
                                         variant=variant, layout=layout, seed=seed, title=title))

    @server.tool()
    def start_episode(task_id: str) -> dict:
        """Start one requested simulation attempt. Save its exact run_id; wait with task_context until ready."""
        return request(f'/api/tasks/{task_id}/start', {})

    def remember_requirement(task_id: str, text: str, run_id: str) -> dict:
        """Persist a requirement only when the user asks to remember it. It remains unverified user input, not successful experience."""
        return request(f'/api/tasks/{task_id}/corrections', dict(text=text, run_id=run_id))

    @server.tool(annotations=readonly)
    def task_context(run_id: str, wait_seconds: Annotated[int, Field(ge=0, le=5)] = 0) -> dict:
        """Read this run's requirements, episode instructions and result. wait_seconds must be 0–5, never longer.

        Short waits let the conversation receive new guidance between steps.
        """
        if not 0 <= wait_seconds <= 5:
            raise ToolError('wait_seconds must be between 0 and 5; return regularly to receive user guidance')
        if wait_seconds:
            time.sleep(wait_seconds)
        return request(f"/api/runs/{run_id}/context")

    @server.tool(annotations=readonly)
    def episode_tools(run_id: str) -> dict:
        """Get native tool names, descriptions and input schemas for this episode's support profile."""
        return request(f"/api/runs/{run_id}/tools")

    @server.tool()
    def robot_call(run_id: str, call_id: str, tool: str, arguments: dict) -> CallToolResult:
        """Call one advertised native tool. Always supply its exact schema and a unique call_id.

        Returns original MCP content including current RGB images. No retries of uncertain motion.
        Do not run robot tools via shell, direct HTTP or any other bypass of this bridge.
        """
        return CallToolResult.model_validate(request(f"/api/runs/{run_id}/call", dict(call_id=call_id, tool=tool, arguments=arguments)))

    @server.tool()
    def finish_episode(run_id: str) -> dict:
        """Ask the native simulator to finalize this episode and produce its actual result; does not assert success."""
        return request(f"/api/runs/{run_id}/finish", {})

    @server.tool()
    def stop_episode(run_id: str) -> dict:
        """End the runner and simulator processes. The interrupted run is not a scored success."""
        return request(f"/api/runs/{run_id}/stop", {})

    if not basic:
        server.tool(annotations=readonly)(view_experience)
        server.tool()(remember_requirement)
    return server


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    from urllib.parse import urlsplit
    parser = argparse.ArgumentParser()
    parser.add_argument('--basic', action='store_true')
    parser.add_argument('--connection', type=Path)
    args = parser.parse_args()
    if args.connection:
        connection = json.loads(args.connection.read_text())
        endpoint = urlsplit(connection['url'])
        if endpoint.scheme != 'http' or endpoint.hostname != '127.0.0.1':
            raise ValueError('LinkMind requires a local service')
        os.environ['LINKMIND_STUDIO_URL'] = connection['url']
        os.environ['LINKMIND_STUDIO_TOKEN'] = connection['token']
    create_server(basic=args.basic).run()
