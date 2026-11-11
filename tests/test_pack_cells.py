"""Exercise calibrated references through the real isolated persistent cell path."""
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from roborag.mcp.server import create_server
from roborag.scene_registration import project
from roborag.scene_transfer import reference_observation
from roborag.toast_motion import enable_toast_guard, dispatch_robot_request
from tests import test_python_cells as cells
from tests import test_toast_motion as motion
from tests.test_scene_transfer import fixture, camera


class PackCellTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await cells.CellTests.asyncSetUp(self)
        self.memory.task = 'pack_objects_into_box'
        train = Path(self.temp.name)/'train.h5'
        fixture(train)
        state, images = reference_observation(train, 0)
        self.state = dict(step=0, episode_over=False, **state)
        for side in ['left','right']:
            self.state['action_state'][f'{side}_ee_joint_state'] = [.7]
        for name, raw in images.items():
            (self.memory.workspace/f'obs/{name}.png').write_bytes(raw)
        class Bank:
            def graph(self, source): return dict(source=dict(sha256='fixture', frames=9))
            def source(self, graph): return train
        self.memory.bank = Bank()
        self.memory.references = {'demo:p1'}
        self.server = create_server(self.memory)
        self.kernel = self.memory.python_cells

    asyncTearDown = cells.CellTests.asyncTearDown
    cell = cells.CellTests.cell
    test_persistence_and_isolation = cells.CellTests.test_real_protocol_persistence_output_images_and_isolation
    test_stationary_gripper = cells.CellTests.test_gripper_hold_bypasses_cartesian_motion_and_preserves_other_arm

    async def test_reference_images_and_values_persist_without_motion_until_chosen(self):
        result, content = await self.cell("ref=robo.inspect_reference('demo:p1',[0,4]); ref['total_frames']")
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['value'], '9')
        self.assertEqual(result['action_steps'], 0)
        self.assertEqual(sum(c.type=='image' for c in content.content), 3)
        labels=[c.text for c in content.content if c.type=='text']
        self.assertIn('HISTORICAL demo:p1 frame 0 head', labels)
        self.assertIn('HISTORICAL demo:p1 frame 4 head', labels)
        points = [[-.1,0,1],[.1,0,1],[0,.12,1]]
        pairs = [dict(reference={'head':project(camera(),point).tolist()},
                      current={'head':project(camera(),point).tolist()},reference_z=1,current_z=1) for point in points]
        result, content = await self.cell(f"anchor=robo.match_reference('demo:p1',0,'object',{pairs!r}); anchor['rms_m']")
        self.assertIsNone(result['error'], result)
        self.assertLess(float(result['value']), 1e-10)
        self.assertEqual(result['action_steps'], 0)
        self.assertTrue(any(c.type=='text' and c.text.startswith('CURRENT object') for c in content.content))
        result,_ = await self.cell("path=robo.prepare_reference('demo:p1',0,8,'right',[dict(frame=0,anchor_id=anchor['anchor_id'])]); path['source_arm']")
        self.assertIsNone(result['error'], result)
        self.assertEqual(ast.literal_eval(result['value']), 'right')
        self.assertFalse(self.submissions)
        # A saved reference cannot bypass the model-owned plan requirement.
        result,_ = await self.cell("robo.move('right',xyz=path['final_target']['tcp_xyz'],steps=4,gripper=.31)")
        self.assertIn('record_plan', result['error'])
        self.assertFalse(self.submissions)
        self.memory.plan = {'steps':['use chosen reference']}
        result,_ = await self.cell("target=path['final_target']; robo.move('right',xyz=target['tcp_xyz'],quaternion=target['quaternion_wxyz'],steps=4,gripper=.31)")
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['action_steps'], 4)
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual([row[13] for row in self.submissions[0]['actions']], [.31]*4)
        self.assertEqual([row[6] for row in self.submissions[0]['actions']], [.7]*4)

    async def test_uncited_reference_and_no_rag_cannot_read_train(self):
        result,_ = await self.cell("robo.inspect_reference('unknown:p1',[0])")
        self.assertIn('Select a cited source',result['error'])
        self.assertFalse(self.submissions)
        await self.kernel.close()
        self.memory.no_rag = True
        self.server=create_server(self.memory); self.kernel=self.memory.python_cells
        result,_ = await self.cell("robo.inspect_reference('demo:p1',[0])")
        self.assertIn('Unknown public method', result['error'])
        self.assertFalse(self.submissions)

    async def test_truncated_reference_motion_stops_later_grip(self):
        self.memory.plan={'steps':['short move']}; self.truncate=True
        result,_ = await self.cell("""robo.move('right',xyz=[.17,0,1],steps=4)
try:
    robo.grip('right',0)
except RuntimeError as exc:
    print(exc)
""")
        self.assertEqual(result['action_steps'],1)
        self.assertTrue(result['motion_stopped'])
        self.assertEqual(len(self.submissions),1)
        self.assertIn('Motion stopped',result['stdout'])


class PackDispatchTests(unittest.TestCase):
    def test_pack_guard_and_measured_joint_grip_use_existing_boundary(self):
        for task in ['pack_objects_into_box','pack_objects_into_box_random']:
            api=motion.delta_api(reject_at=1)
            enable_toast_guard(api,task,Path('/tmp'))
            self.assertEqual(api._env.ik_continuity_guard.limit,.25)
            row=[0,0,0,0,0,0,.6,.01,0,0,0,0,0,.6]
            rejected=[0,0,0,0,0,0,0,.01,0,0,0,0,0,0]
            result=dispatch_robot_request(api,{'actions':[row,rejected,row]},task)
            self.assertEqual((result['action_steps'],result['discarded_rows']),(1,2))
            self.assertFalse(result['rejection']['rejected_action_executed'])
            self.assertEqual(api.arm('right').gripper_target,.6)
            with patch('roborag.toast_motion.execute_joint_hold',return_value='held') as hold:
                self.assertEqual(dispatch_robot_request(api,{'joint_hold':{'steps':4}},task),'held')
                hold.assert_called_once()


if __name__=='__main__':
    unittest.main()
