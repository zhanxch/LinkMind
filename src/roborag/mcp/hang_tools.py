"""Optional current-image measurements for hang_mugs, without action dispatch."""
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from roborag.hang_measurements import measure_public_rgb

ROOT = Path(__file__).resolve().parents[3]


def register_tools(server, memory, read_only):
    @server.tool(annotations=read_only)
    async def measure_mug_geometry(
            command: Literal['surface', 'stereo_guide', 'peg_measure', 'aperture'],
            arguments: dict) -> dict:
        """Optional RGB/calibration geometry, zero control steps; no holding or task-success sensor.

        Select pixels yourself from current images; matching the same physical point
        across cameras is your responsibility. camera='head', camera2='wrist_r'
        by default; either may also be wrist_l. Pixel arguments accept [u,v],
        [[u,v],...] or 'u,v;u,v' text, using ORIGINAL image coordinates.
        surface: pixels plus matching pixels2, OR your measured horizontal height z.
        stereo_guide: pixels, optional pixels2 -> epipolar correspondence diagnostics.
        peg_measure: tip/root in camera, tip2/root2 in camera2, and edges and/or
        edges2 on BOTH long silhouette sides -> tip, root, root-to-tip axis and radius.
        aperture: 4-32 matched INNER boundary points rim/rim2, center=[u,v] in
        camera -> center, plane normal and conservative clear radius. It assumes
        a planar opening; a solid surface or wrong correspondence is not certified.
        Failed/weak measurements change no robot state. These tools are optional;
        choose new views, direct triangulation or another approach as appropriate.
        """
        async with memory.lock:
            state = memory.state()
            try:
                result = measure_public_rgb(memory.workspace, state, ROOT / 'vendor/HexaShell', command, arguments)
            except (ValueError, KeyError, TypeError) as exc:
                memory.audit('measure_mug_geometry', dict(command=command, arguments=arguments),
                             dict(error=str(exc), measured_at_step=state['step'], action_steps=0))
                raise ToolError(str(exc)) from exc
            memory.audit('measure_mug_geometry', dict(command=command, arguments=arguments), result)
            return result
