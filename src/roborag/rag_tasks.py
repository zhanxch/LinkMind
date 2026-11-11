"""Task instructions stay separate from the robot protocol and process runner."""
from pathlib import Path

GENERALIZATION_TASKS = {
    "stack_bowls", "pack_objects_into_box", "hang_mugs", "sweep_blocks",
    "pour_liquid_into_cup", "make_toast", "arrange_largest_number",
    "sort_nesting_dolls_by_size", "store_laptop_and_headphones",
}
TASKS = {"stack_blocks", "fold_clothes", "push_T", *GENERALIZATION_TASKS}


def simulation_task(task, variant):
    if task not in TASKS or variant not in ("standard", "random"):
        raise ValueError("Unsupported task or scene variant")
    return task + ("_random" if variant == "random" else "")


def public_task_instruction(observation):
    """Forward only the language field in RoboDojo's public observation."""
    instruction = observation.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("Native public task instruction is missing or invalid")
    return instruction


def prompt_for(root, task, controller, *, no_rag=False):
    simulation_task(task, "standard")
    directory = Path(root) / "prompts"
    specific = directory / f"{task}.{controller}.txt"
    if specific.is_file():
        prompt = specific.read_text()
    elif controller == "delta":
        protocol = "robot.generalization.delta.txt" if task in GENERALIZATION_TASKS | {"push_T"} else "robot.delta.txt"
        prompt = (directory / f"{task}.txt").read_text() + "\n\n" + (directory / protocol).read_text()
    else:
        raise ValueError(f"No {controller} protocol configured for {task}")
    if task == "pack_objects_into_box" and controller == "delta" and not no_rag:
        from .scene_transfer import transfer_prompt
        prompt = transfer_prompt(prompt)
    if no_rag:
        prompt += "\n\nCONTROL CONDITION: Historical retrieval is disabled in this episode. Call retrieve_evidence once for the empty control record, then record your plan with evidence_refs=[]. Do not call read_action_reference or invent sources. All instructions above to expand demonstrations are inapplicable."
    return prompt
