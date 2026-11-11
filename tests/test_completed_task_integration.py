"""Compare the merged interfaces to each evaluated task's original candidate.

The fixture was captured from the eight source candidates, not the merge.
Simulator wiring is exercised without starting Isaac Sim or an online model.
"""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from mcp import Client
from roborag.rag_mcp import EpisodeMemory, create_server
from roborag.rag_tasks import prompt_for
from roborag.episode_budget import apply_control_budget
from tests.test_toast_motion import enable_toast_guard, IKContinuityError

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = json.loads((ROOT / "tests/fixtures/completed-task-contracts.json").read_text())


class CompletedTaskInterfaces(unittest.IsolatedAsyncioTestCase):
    async def test_all_eight_candidate_interfaces_and_ablation_interfaces(self):
        for task, contract in CONTRACTS.items():
            for no_rag in (False, True):
                with self.subTest(task=task, no_rag=no_rag), tempfile.TemporaryDirectory() as tmp:
                    memory = EpisodeMemory(tmp, tmp, tmp, tmp, task, controller="delta", no_rag=no_rag)
                    async with Client(create_server(memory)) as client:
                        tools = [t.model_dump(mode="json", exclude_none=True)
                                 for t in (await client.list_tools()).tools]
                    prompt = prompt_for(ROOT, task, "delta", no_rag=no_rag)
                    expected = contract["no_rag" if no_rag else "rag"]
                    self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), expected["prompt_sha256"])
                    encoded = json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    self.assertEqual(hashlib.sha256(encoded.encode()).hexdigest(), expected["tools_sha256"])
                    self.assertEqual([t["name"] for t in tools], expected["tool_names"])


class SimulatorIntegration(unittest.TestCase):
    def test_each_variant_keeps_its_original_guard_and_dispatch(self):
        tree = ast.parse((ROOT / "src/roborag/rag_sim.py").read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        body = next(n for n in main.body if isinstance(n, ast.Try)).body
        start = next(i for i, n in enumerate(body) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "budget" for t in n.targets))
        end = next(i for i, n in enumerate(body) if isinstance(n, ast.FunctionDef) and n.name == "publish_ready")
        init = compile(ast.Module(body=body[start:end], type_ignores=[]), "rag_sim:init", "exec")
        dispatch = next(n for n in ast.walk(main) if isinstance(n, ast.If)
                        and isinstance(n.test, ast.Compare)
                        and isinstance(n.test.left, ast.Constant) and n.test.left.value == "planar_measure")
        dispatch = compile(ast.Module(body=[dispatch], type_ignores=[]), "rag_sim:dispatch", "exec")
        guarded = {"push_T", "make_toast", "hang_mugs", "sweep_blocks", "pack_objects_into_box"}
        for task in CONTRACTS:
            for suffix in ("", "_random"):
                with self.subTest(task=task + suffix):
                    env = SimpleNamespace(step_lim=500)
                    api_factory = Mock(side_effect=lambda env, output, **kw: SimpleNamespace(_env=env))
                    scope = dict(env=env, args=SimpleNamespace(control_step_limit=None), task=task + suffix,
                                 output=Path("/tmp"), LiveAPI=api_factory, apply_control_budget=apply_control_budget,
                                 enable_toast_guard=enable_toast_guard)
                    exec(init, scope)
                    self.assertEqual(scope["budget"]["step_limit"], 500)
                    self.assertEqual(hasattr(env, "ik_continuity_guard"), task in guarded)
                    if task in guarded:
                        self.assertEqual(env.ik_continuity_guard.limit, .25)
                    self.assertEqual(scope["rejection_errors"], (IKContinuityError,) if task == "push_T" else ())
                    self.assertEqual(api_factory.call_args.kwargs["task_instruction"], task == "push_T")
                    for request in ({"actions": [[0] * 14]}, {"chunk": {}}):
                        delta, chunk, specialized = Mock(), Mock(), Mock()
                        scope.update(request=request, execute_delta_actions=delta, execute_chunk=chunk,
                                     dispatch_robot_request=specialized)
                        exec(dispatch, scope)
                        if task == "push_T":
                            specialized.assert_not_called()
                            if "actions" in request:
                                delta.assert_called_once_with(scope["api"], request["actions"],
                                                              rejection_errors=(IKContinuityError,))
                                chunk.assert_not_called()
                            else:
                                chunk.assert_called_once_with(scope["api"], request["chunk"])
                                delta.assert_not_called()
                        else:
                            specialized.assert_called_once_with(scope["api"], request, task + suffix)
                            delta.assert_not_called()
                            chunk.assert_not_called()
