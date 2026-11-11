"""Cumulative Push_T simplifications; baseline and physical control stay intact."""
import json
from pathlib import Path
from typing import Literal

PROFILES = ("baseline", "summaries", "no_plan", "fixed", "none")
ROOT = Path(__file__).resolve().parents[2]
FIXED_SOURCES = {"right": "push_T-0000:p01", "left": "push_T-0001:p01"}
FIXED_PACKAGE = ROOT / "artifacts/push-t-simplification/fixed-references.json"


def validate_profile(profile, task, controller, no_rag=False):
    if profile not in PROFILES:
        raise ValueError("Unknown Push_T simplification profile")
    if profile != "baseline" and (task != "push_T" or controller != "delta" or no_rag):
        raise ValueError("Simplification requires push_T/delta; use profile=none instead of --no-rag")


def prompt_for_profile(prompt, profile):
    if profile == "baseline":
        return prompt
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    prompt = prompt.replace(" with include_actions=false", "")
    prompt = prompt.replace("; use include_actions=true only if exact rows are needed.", ".")
    if profile == "summaries":
        return prompt
    prompt = prompt.replace("Then record YOUR new plan, object bindings, completion observations and adopted evidence IDs.",
                            "Reason about your plan from the available observations and evidence; no plan-recording tool is required.")
    if profile == "no_plan":
        return prompt
    start = prompt.index("Using interaction evidence (when retrieval is enabled):")
    stop = prompt.index("Use execute_chunk for all robot movement.", start)
    workflow = ("First observe current head and wrist RGB with calibration=true. "
                "Choose targets, contact and short actions from current RGB, calibration and proprioception. ")
    if profile == "fixed":
        workflow += ("read_reference(arm='left' or 'right') provides one fixed TRAIN preparation example for that arm, "
                     "with recorded state summaries and images. Use it when useful; it is not a current target or a prescribed motion. "
                     "The two references are fixed before evaluation; there is no search, graph browsing or citation prerequisite. ")
    else:
        workflow += "No historical demonstrations are provided. "
    workflow += "Plan as needed; execute_chunk can be called directly after observation.\n\n"
    prompt = prompt[:start] + workflow + prompt[stop:]
    replacements = {
        "from live RGB and TRAIN context": "from live RGB and robot state",
        "do not treat a historical tilted wrist as mandatory": "choose a wrist orientation that maintains planar side contact",
        "retrieved TRAIN evidence": "available information",
        "Historical object positions, identities and event sequences are examples, not current targets. ": "",
        "The live interface matches recorded 14D world link6 delta actions.": "The live interface uses 14D world link6 delta actions.",
        "Use the demonstrated wrist quaternion as an orientation reference, adapt if reach or contact feedback requires it, and keep it unchanged during translation when suitable.": "Choose the wrist quaternion from current contact geometry and reach; keep it unchanged during translation when suitable.",
        "A world-frame reference action is an example, never a trajectory to replay blindly. ": "",
        "Follow that current instruction and current RGB, not the object identities or order in a historical demonstration.": "Follow that current instruction and current RGB.",
        "Do not infer a live sequence from the TRAIN example.": "Infer any live sequence from current observations.",
    }
    for old, new in replacements.items():
        prompt = prompt.replace(old, new)
    return prompt


class CaptureTools:
    """Capture existing evidence callbacks without changing their payloads."""
    def __init__(self):
        self.functions = {}

    def tool(self, **kwargs):
        def register(fn):
            self.functions[kwargs.get("name", fn.__name__)] = fn
            return fn
        return register


def evidence_callbacks(memory, annotations):
    from roborag.mcp import evidence
    captured = CaptureTools()
    evidence.register_tools(captured, memory, annotations)
    return captured.functions


def create_simplified_server(memory):
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations, CallToolResult
    from roborag.mcp import observations, planning, motion
    profile = memory.push_simplification
    validate_profile(profile, memory.task, memory.controller, memory.no_rag)
    instructions = ("First observe, retrieve relevant historical evidence, then record YOUR new plan. "
                    "Historical graphs are examples, not executable plans. Ground every TCP in current images. "
                    "execute_chunk is a short batch of your new actions; it returns current images and measured robot state.")
    if profile == "no_plan":
        instructions = instructions.replace("then record YOUR new plan.", "then reason about your plan; no plan-recording tool is required.")
    elif profile in ("fixed", "none"):
        instructions = ("First observe current RGB and calibration, then reason about your plan and generate short actions. "
                        "Ground every TCP in current images. execute_chunk returns current images and measured robot state. "
                        "The native environment determines completion.")
        if profile == "fixed":
            instructions += " Fixed historical references are available by arm when useful."
    server = MCPServer("RoboRAG", instructions=instructions)
    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    if profile in ("summaries", "no_plan"):
        callbacks = evidence_callbacks(memory, read_only)
        description = callbacks["retrieve_evidence"].__doc__.replace(
            "Raw action arrays/images stay behind read_action_reference to keep context small.",
            "Historical summaries/images stay behind read_action_reference to keep context small.")
        server.add_tool(callbacks["retrieve_evidence"], annotations=read_only, description=description)

        @server.tool(annotations=read_only)
        def read_action_reference(source: str, images: bool = True,
                                  section: Literal["start", "end", "close", "open"] = "start") -> CallToolResult:
            """Expand a retrieved source into historical state/operation/feedback and images.

            start/end select a phase boundary; close/open select a recorded gripper command event.
            Events do not prove contact. Coordinates and wrist poses are historical examples.
            The original measured summaries and whole-phase images are preserved; raw action arrays are unavailable.
            """
            return callbacks["read_action_reference"](source, include_actions=False, images=images, section=section)
    elif profile == "fixed":
        package = json.loads(FIXED_PACKAGE.read_text())
        if package["sources"] != FIXED_SOURCES:
            raise ValueError("Fixed TRAIN references do not match the registered selection")
        memory.bank = None

        @server.tool(annotations=read_only)
        def read_reference(arm: Literal["left", "right"]) -> CallToolResult:
            """One fixed TRAIN preparation example for the selected arm: states, summaries and images.

            These are historical poses and command events, not current geometry or proven contact.
            Choose current contact, wrist orientation and motion from live observations.
            """
            result = CallToolResult.model_validate(package["references"][arm])
            memory.audit("read_reference", dict(arm=arm), dict(source=FIXED_SOURCES[arm],
                         packet=json.loads(result.content[0].text), image_count=sum(c.type=="image" for c in result.content)))
            return result
    else:
        memory.bank = None
    observations.register_tools(server, memory, read_only)
    if profile == "summaries":
        planning.register_tools(server, memory, read_only)
    motion.register_tools(server, memory, read_only, require_plan=profile == "summaries")
    return server


def workflow_for_profile(calls, profile):
    from roborag.rag_accounting import workflow_completed
    if profile in ("baseline", "summaries"):
        return workflow_completed(calls)
    names = [c["tool"] for c in calls]
    prohibited = {"record_plan"}
    if profile in ("fixed", "none"):
        prohibited |= {"retrieve_evidence", "read_action_reference"}
    if profile == "none":
        prohibited.add("read_reference")
    return ("observe" in names and "execute_chunk" in names
            and names.index("observe") < names.index("execute_chunk")
            and not prohibited.intersection(names))
