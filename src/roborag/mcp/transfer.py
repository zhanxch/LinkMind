"""Opt-in scene correspondence and read-only TRAIN motion references."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from scipy.spatial.transform import Rotation
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ImageContent, TextContent

from roborag.scene_registration import fit_rigid, locate_landmark
from roborag.scene_transfer import (CAMERAS, build_trajectory,
                                   measure_table, reference_observation, tcp_target)




class LandmarkPair(BaseModel):
    reference: dict[str, list[float]] = Field(description="Camera -> [u,v] of the SAME feature in TRAIN")
    current: dict[str, list[float]] = Field(description="Camera -> [u,v] of the corresponding CURRENT feature")
    reference_z: float | None = Field(default=None, description="World height assumption for single-view reference point")
    current_z: float | None = Field(default=None, description="World height assumption for single-view current point")


class TransformKnot(BaseModel):
    frame: int
    anchor_id: str
    offset_xyz: list[float] = Field(default_factory=lambda: [0., 0., 0.], description="Explicit planner target offset in world metres")
    yaw_offset_degrees: float = Field(default=0., description="Rotate the whole reference path about the matched landmark center; changes the grasp point, not just the wrist")


def register_tools(server, memory, read_only):
    anchors, table_cache = {}, {}
    tool_path = Path(__file__).resolve().parents[3] / "vendor/HexaShell/tools/table_plane/tool.py"

    def source_path(source):
        if source not in memory.references or memory.no_rag:
            raise ValueError("Select a cited source from retrieve_evidence first")
        graph = memory.bank.graph(source.split(":", 1)[0])
        return memory.bank.source(graph), graph

    def pack(packet, images=()):
        content = [TextContent(type="text", text=json.dumps(packet, ensure_ascii=False, separators=(",", ":")))]
        for label, raw in images:
            content.extend([TextContent(type="text", text=label), ImageContent(type="image", mimeType="image/png" if raw.startswith(b"\x89PNG") else "image/jpeg", data=base64.b64encode(raw).decode())])
        return CallToolResult(content=content)

    def marked(raw, pairs, key, camera):
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        draw = ImageDraw.Draw(im)
        for i, pair in enumerate(pairs):
            if camera in pair[key]:
                u, v = pair[key][camera]
                draw.ellipse((u - 4, v - 4, u + 4, v + 4), outline="cyan", width=2)
                draw.text((u + 5, v - 8), str(i + 1), fill="cyan")
        out = io.BytesIO(); im.save(out, format="PNG")
        return out.getvalue()

    @server.tool(annotations=read_only)
    async def inspect_transfer_reference(source: str, frames: list[int],
            cameras: list[Literal["head", "wrist_l", "wrist_r"]] = ["head"],
            measure_support: bool = False) -> CallToolResult:
        """Inspect 1-6 exact TRAIN frames for scene alignment and interval selection.

        source is a retrieved graph:phase citation; frames may span its whole demo.
        Returns measured TCP/gripper states and historical images at original pixels.
        measure_support measures TRAIN/current table height from RGB stereo, no truth.
        All image pixel coordinates use the original 640x480 frame, not a resized crop.
        """
        try:
            path, graph = source_path(source)
            if not 1 <= len(frames) <= 6 or not cameras:
                raise ValueError("Select 1-6 frames and at least one camera")
            async with memory.lock:
                entries, images = [], []
                for frame in frames:
                    observation, raw = reference_observation(path, frame)
                    state = observation["action_state"]
                    entry = dict(frame=frame, tcp={arm: tcp_target(state[f"{arm}_ee_pose"], state[f"{arm}_ee_joint_state"][0]) for arm in ("left", "right")})
                    if measure_support:
                        key = (str(path), frame)
                        if key not in table_cache:
                            table_cache[key] = measure_table(raw, observation["cameras"], tool_path)
                        entry["table_measurement"] = table_cache[key]
                    entries.append(entry)
                    images.extend((f"HISTORICAL {source} frame {frame} {cam}", raw[cam]) for cam in cameras)
                packet = dict(source=source, source_sha256=graph["source"]["sha256"], frames=entries,
                              total_frames=graph["source"]["frames"], dimensions=[640, 480])
                if measure_support:
                    live = memory.state()
                    key = ("current", live["step"])
                    if key not in table_cache:
                        raw = {cam: (memory.workspace / f"obs/{cam}.png").read_bytes() for cam in CAMERAS}
                        table_cache[key] = measure_table(raw, live["cameras"], tool_path)
                    packet["current_table_measurement"] = table_cache[key]
                memory.audit("inspect_transfer_reference", dict(source=source, frames=frames, cameras=cameras, measure_support=measure_support), packet)
                return pack(packet, images)
        except (ValueError, KeyError) as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=read_only)
    async def match_scene_reference(source: str, reference_frame: int, label: str,
            landmarks: list[LandmarkPair], mode: Literal["planar", "rigid"] = "planar",
            max_error_m: float = .02) -> CallToolResult:
        """Fit a source-to-current object/scene transform from corresponding RGB points.

        Landmarks are ordered matching physical features, not unrelated box centers.
        For each point supply reference/current camera->[u,v]; >=2 cameras triangulate.
        A single camera requires explicit reference_z/current_z surface heights.
        Planar needs >=2 distinct landmarks, full rigid >=3 noncollinear. More points
        expose mismatch. No scaling. Fit residual does not measure height-assumption
        error. Returns saved anchor_id, transform, residual and annotated RGB.
        """
        try:
            path, graph = source_path(source)
            if not 2 <= len(landmarks) <= 12:
                raise ValueError("Select 2-12 corresponding landmarks")
            pairs = [p.model_dump() for p in landmarks]
            async with memory.lock:
                reference, ref_images = reference_observation(path, reference_frame)
                live = memory.state()
                reference_xyz, current_xyz, measurements = [], [], []
                for pair in pairs:
                    a, ma = locate_landmark(reference["cameras"], pair["reference"], pair["reference_z"])
                    b, mb = locate_landmark(live["cameras"], pair["current"], pair["current_z"])
                    reference_xyz.append(a); current_xyz.append(b)
                    measurements.append(dict(reference=ma, current=mb))
                result = fit_rigid(reference_xyz, current_xyz, mode, max_error_m)
                result.update(source=source, source_sha256=graph["source"]["sha256"], reference_frame=reference_frame,
                              label=label, measured_at_step=live["step"], landmarks=pairs, measurements=measurements,
                              reference_xyz=np.asarray(reference_xyz).tolist(), current_xyz=np.asarray(current_xyz).tolist())
                anchor_id = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
                result["anchor_id"] = anchor_id
                anchors[anchor_id] = result
                images = []
                for key, raws in (("reference", ref_images), ("current", {c: (memory.workspace / f"obs/{c}.png").read_bytes() for c in CAMERAS})):
                    for cam in CAMERAS:
                        if any(cam in p[key] for p in pairs):
                            images.append((f"{key.upper()} {label} numbered matches {cam}", marked(raws[cam], pairs, key, cam)))
                memory.audit("match_scene_reference", dict(source=source, reference_frame=reference_frame, label=label,
                             landmarks=pairs, mode=mode, max_error_m=max_error_m), result)
                return pack(result, images)
        except (ValueError, KeyError) as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=read_only)
    async def prepare_motion_transfer(source: str, start_frame: int, end_frame: int,
            arm: Literal["left", "right"], knots: list[TransformKnot],
            source_arm: Literal["left", "right"] | None = None) -> dict:
        """Compute geometric references from TRAIN interval [start,end), without moving.

        Select up to 600 source rows. arm is the intended CURRENT hand; source_arm
        is the recorded hand and defaults to arm. Cross-arm references preserve
        world gripper pose; they do not mirror the grasp or prove reachability.
        Each knot is {frame,anchor_id,offset_xyz?,yaw_offset_degrees?}. One knot is a
        rigid transfer. Multiple knots smoothly blend transforms between specified
        frames for FREE transport; constant outside first/last knot. Choose knot
        times so contact/grasp/release intervals retain the appropriate anchor.
        Goal offsets are explicit planner changes, separate from measured alignment.
        A yaw offset rotates the entire path about the matched landmark center,
        changing both grasp position and orientation. It is not a wrist-only turn.
        Returns entry/first/final TCP poses and path samples, not an execution queue.
        Frames and gripper values describe TRAIN; select current execution timing
        and grip from live contact feedback using execute_chunk targets.
        """
        try:
            path, graph = source_path(source)
            values, anchor_records = [], []
            for knot in knots:
                a = anchors[knot.anchor_id]
                if a["source"].split(":")[0] != source.split(":")[0]:
                    raise ValueError("All anchors must refer to the same TRAIN demonstration")
                offset = np.asarray(knot.offset_xyz, float)
                if offset.shape != (3,) or not np.isfinite(offset).all() or not np.isfinite(knot.yaw_offset_degrees):
                    raise ValueError("Invalid explicit goal offset")
                adjust = np.eye(4)
                adjust[:3, :3] = Rotation.from_euler("z", knot.yaw_offset_degrees, degrees=True).as_matrix()
                center = np.asarray(a["current_center"])
                adjust[:3, 3] = center - adjust[:3, :3] @ center + offset
                values.append(dict(frame=knot.frame, matrix=(adjust @ np.asarray(a["matrix"])).tolist()))
                anchor_records.append(dict(**knot.model_dump(), measured_at_step=a["measured_at_step"]))
            source_arm = arm if source_arm is None else source_arm
            trajectory = build_trajectory(path, start_frame, end_frame, arm, values, source_arm=source_arm)
            request = dict(source=source, start_frame=start_frame, end_frame=end_frame, arm=arm, source_arm=source_arm,
                           knots=[k.model_dump() for k in knots])
            plan_id = hashlib.sha256(json.dumps(dict(request=request, transforms=values), sort_keys=True).encode()).hexdigest()[:16]
            samples = sorted(set(np.linspace(0, end_frame - start_frame - 1, min(8, end_frame - start_frame), dtype=int).tolist()))
            packet = dict(plan_id=plan_id, source=source, source_sha256=graph["source"]["sha256"],
                          interval=[start_frame, end_frame], total_rows=end_frame-start_frame, arm=arm, source_arm=source_arm,
                          anchors=anchor_records, transforms=values,
                          entry_target=trajectory["entry_target"], first_target=trajectory["first_target"],
                          final_target=trajectory["final_target"],
                          path_samples=[dict(frame=start_frame+i, **tcp_target(trajectory["poses"][i], trajectory["grippers"][i])) for i in samples],
                          limitation="Geometric references only, not an execution queue. Choose current timing and grip from live feedback; check reachability, contact and world-facing task goal.")
            memory.audit("prepare_motion_transfer", request, packet)
            return packet
        except (ValueError, KeyError) as exc:
            raise ToolError(str(exc)) from exc
