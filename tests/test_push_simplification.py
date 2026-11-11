import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from mcp import Client
from mcp.types import CallToolResult, TextContent
from roborag.mcp.session import EpisodeMemory
from roborag.mcp.server import create_server
from roborag.rag_tasks import prompt_for
from roborag.push_simplification import ROOT, PROFILES, FIXED_PACKAGE, FIXED_SOURCES, prompt_for_profile, validate_profile, workflow_for_profile

BANK = ROOT / "artifacts/generalization-v3-full/push_T"


class SimplificationTests(unittest.IsolatedAsyncioTestCase):
    def memory(self, temp, profile):
        m = EpisodeMemory(BANK, ROOT / "data", temp, temp, "push_T", controller="delta")
        m.push_simplification = profile
        m.state = lambda: dict(step=0, episode_over=False, action_state={
            "left_ee_pose":[-.3,0,1,1,0,0,0],"right_ee_pose":[0,0,1,1,0,0,0],
            "left_ee_joint_state":[1],"right_ee_joint_state":[1]})
        m.submit = AsyncMock(return_value=dict(result=dict(step=1, episode_over=False, executed_rows=1)))
        m.observation = lambda *a, **kw: CallToolResult(content=[TextContent(type="text", text="current RGB receipt")])
        return m

    async def test_surfaces_and_direct_execution_no_dummy_plan(self):
        expected = {
            "baseline": {"retrieve_evidence", "read_action_reference", "measure_planar", "observe", "record_plan", "execute_chunk"},
            "summaries": {"retrieve_evidence", "read_action_reference", "measure_planar", "observe", "record_plan", "execute_chunk"},
            "no_plan": {"retrieve_evidence", "read_action_reference", "measure_planar", "observe", "execute_chunk"},
            "fixed": {"read_reference", "measure_planar", "observe", "execute_chunk"},
            "none": {"measure_planar", "observe", "execute_chunk"},
        }
        for profile in PROFILES:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temp:
                m = self.memory(temp, profile)
                async with Client(create_server(m)) as c:
                    tools = (await c.list_tools()).tools
                    self.assertEqual({t.name for t in tools}, expected[profile])
                    reference = next((t for t in tools if t.name=="read_action_reference"), None)
                    if reference:
                        self.assertEqual("include_actions" in reference.input_schema["properties"],profile=="baseline")
                    result = await c.call_tool("execute_chunk",dict(subgoal="hold",expected_feedback="stationary",
                        actions=[[0,0,0,0,0,0,1,0,0,0,0,0,0,1]]))
                    self.assertEqual(result.is_error,profile in ("baseline","summaries"))
                    self.assertEqual(m.submit.await_count,0 if profile in ("baseline","summaries") else 1)
                    self.assertIsNone(m.plan)
                    self.assertFalse((Path(temp)/"gpt-plan.json").exists())
                    if profile in ("fixed","none"):
                        self.assertIsNone(m.bank)

    @unittest.skipUnless((ROOT / 'data/runtime-data/push_T/train/episode_0000000.hdf5').exists(),
                         'Optional TRAIN integration check: install Push_T demonstrations first')
    async def test_summaries_and_fixed_references_preserve_original_content(self):
        archived = json.loads(FIXED_PACKAGE.read_text())
        for arm,source in FIXED_SOURCES.items():
            responses = []
            for profile in ("baseline","summaries","no_plan","fixed"):
                with tempfile.TemporaryDirectory() as temp:
                    m=self.memory(temp,profile); m.references.add(source)
                    async with Client(create_server(m)) as c:
                        name="read_reference" if profile=="fixed" else "read_action_reference"
                        args=dict(arm=arm) if profile=="fixed" else dict(source=source,section="close",images=True)
                        response=await c.call_tool(name,args)
                        self.assertFalse(response.is_error)
                        responses.append([b.model_dump(mode="json",exclude_none=True) for b in response.content])
                        self.assertNotIn("actions",json.loads(response.content[0].text)["transition"])
            self.assertTrue(all(r==responses[0] for r in responses))
            self.assertEqual(archived['references'][arm]['content'],responses[0])

    async def test_motion_payload_identical_and_limits_unchanged(self):
        valid=[dict(actions=[[0,0,0,0,0,0,1,.001,0,0,0,0,0,1]]),
               dict(segments=[dict(delta=[0,0,0,0,0,0,1,.001,0,0,0,0,0,1],repeat=4)]),
               dict(targets=[dict(steps=4,right=dict(tcp_xyz=[.155,0,1],gripper=1))]),
               dict(return_home=True)]
        for payload in valid:
            receipts=[]
            for profile in PROFILES:
                with tempfile.TemporaryDirectory() as temp:
                    m=self.memory(temp,profile)
                    if profile in ("baseline","summaries"):m.plan={"test_only":True}
                    async with Client(create_server(m)) as c:
                        result=await c.call_tool("execute_chunk",dict(subgoal="test",expected_feedback="test",**payload))
                        self.assertFalse(result.is_error)
                        receipts.append(m.submit.call_args.args[0])
            self.assertTrue(all(x==receipts[0] for x in receipts))
        for profile in PROFILES:
            with tempfile.TemporaryDirectory() as temp:
                m=self.memory(temp,profile);m.plan={"test_only":True}
                async with Client(create_server(m)) as c:
                    result=await c.call_tool("execute_chunk",dict(subgoal="invalid",expected_feedback="none",
                        segments=[dict(delta=[0]*14,repeat=25)]))
                    self.assertTrue(result.is_error);m.submit.assert_not_awaited()

    def test_prompt_physical_guidance_and_scope(self):
        base=prompt_for(ROOT,"push_T","delta")
        self.assertEqual(prompt_for_profile(base,"baseline"),base)
        for profile in PROFILES:
            text=prompt_for_profile(base,profile)
            for guidance in ["maximum joint increment 0.25 rad", "Release stationary before lifting", "Save the initial unobstructed match", "1-24 rows at 25 Hz"]:
                self.assertIn(guidance,text)
            if profile!="baseline":self.assertNotIn("include_actions",text)
            if profile in ("no_plan","fixed","none"):self.assertNotIn("record YOUR new plan",text)
            if profile in ("fixed","none"):
                self.assertNotIn("Retrieve historical evidence",text)
                self.assertNotIn("read_action_reference",text)
            if profile=="none":self.assertNotIn("read_reference",text)
        for task,controller,no_rag in [("fold_clothes","delta",False),("push_T","tcp",False),("push_T","delta",True)]:
            with self.assertRaises(ValueError):validate_profile("none",task,controller,no_rag)
        self.assertTrue(workflow_for_profile([dict(tool=t) for t in ["observe","execute_chunk"]],"none"))
        self.assertFalse(workflow_for_profile([dict(tool=t) for t in ["observe","retrieve_evidence","execute_chunk"]],"none"))


if __name__ == "__main__":unittest.main()
