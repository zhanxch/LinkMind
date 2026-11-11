"""Public geometry, real isolated worker, and unchanged motion bridge contracts."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

from mcp import Client
from roborag.mcp.session import EpisodeMemory
from roborag.mcp.server import create_server
from roborag.mcp.python_worker import pixel_to_plane, triangulate


def synthetic_state():
    cameras = {}
    for camera, x in [('head', -.2), ('wrist_r', .2), ('wrist_l', -.4)]:
        t = np.eye(4); t[0, 3] = x
        cameras[camera] = dict(intrinsics=[[500,0,320],[0,500,240],[0,0,1]],
                               extrinsics_world=t.tolist(), size=[640,480])
    return dict(step=0, episode_over=False, cameras=cameras, action_state={
        f'{side}_{key}': value for side in ['left','right'] for key,value in
        [('ee_pose',[0,0,1,1,0,0,0]),('ee_joint_state',[.7])]})


class GeometryTests(unittest.TestCase):
    def test_camera_snapshots_geometry_and_invalid_baseline(self):
        s = synthetic_state()
        np.testing.assert_allclose(pixel_to_plane(s,'head',[420,240],1), [0,0,1], atol=1e-12)
        r = triangulate([(s,'head',[420,240]),(s,'wrist_r',[220,240])])
        np.testing.assert_allclose(r['xyz'], [0,0,1], atol=1e-12)
        self.assertLess(max(r['reprojection_error_px']),1e-10)
        with self.assertRaises(ValueError):
            triangulate([(s,'head',[420,240]),(s,'head',[420,240])])
        with self.assertRaises(ValueError):
            pixel_to_plane(s,'head',[420,240],-1)
        # Moving a wrist requires its own new extrinsics, not stale calibration.
        moved = copy.deepcopy(s); moved['cameras']['wrist_r']['extrinsics_world'][0][3] = .4
        r = triangulate([(s,'head',[420,240]),(moved,'wrist_r',[120,240])])
        np.testing.assert_allclose(r['xyz'], [0,0,1], atol=1e-12)


class CellTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name); (root/'obs').mkdir()
        self.state = synthetic_state()
        for camera in self.state['cameras']:
            Image.new('RGB',(64,48),(20,40,60)).save(root/f'obs/{camera}.png')
        self.memory = EpisodeMemory(root,root,root,root,'make_toast',controller='delta')
        self.memory.state = lambda: copy.deepcopy(self.state)
        self.submissions = []
        self.truncate = False

        async def submit(request):
            self.submissions.append(request)
            if 'joint_hold' in request:
                h=request['joint_hold']
                if h.get('arm') is not None:
                    self.state['action_state'][h['arm']+'_ee_joint_state']=[h['gripper']]
                self.state['step']+=h['steps']
                return dict(result=dict(action_steps=h['steps'],executed_waypoints=0,
                                        step=self.state['step'],episode_over=False))
            actions = request.get('actions',[])
            executed = actions[:1] if self.truncate else actions
            for row in executed:
                for side,offset in [('left',0),('right',7)]:
                    pose = self.state['action_state'][f'{side}_ee_pose']
                    r = Rotation.from_quat(np.asarray(pose[3:])[[1,2,3,0]])
                    r = Rotation.from_rotvec(row[offset+3:offset+6])*r
                    self.state['action_state'][f'{side}_ee_pose'] = [
                        *(np.asarray(pose[:3])+row[offset:offset+3]),*r.as_quat()[[3,0,1,2]]]
                    self.state['action_state'][f'{side}_ee_joint_state'] = [row[offset+6]]
                self.state['step'] += 1
            return dict(result=dict(submitted_rows=len(actions), executed_rows=len(executed),
                discarded_rows=len(actions)-len(executed), action_steps=len(executed),
                step=self.state['step'], episode_over=False))
        self.memory.submit = submit
        self.server = create_server(self.memory)
        self.kernel = self.memory.python_cells

    async def asyncTearDown(self):
        await self.kernel.close()
        self.temp.cleanup()

    async def cell(self, code, **kw):
        result = await self.kernel.run(code, ['head'], **kw)
        return json.loads(result.content[0].text), result

    async def test_prefixed_geometry_helpers_work_across_cells_without_motion(self):
        value,_=await self.cell("""snapshot=robo.state()
point=robo.pixel_to_plane(snapshot,'head',[420,240],1)
np.testing.assert_allclose(point,[0,0,1],atol=1e-12)
views=[(snapshot,'head',[420,240]),(snapshot,'wrist_r',[220,240])]
np.testing.assert_allclose(robo.triangulate(views)['xyz'],point,atol=1e-12)
pos,rotation=robo.tcp_pose(snapshot,'right')
np.testing.assert_allclose(pos,[.145,0,1],atol=1e-12)
np.testing.assert_allclose(rotation.as_matrix(),np.eye(3),atol=1e-12)
""")
        self.assertIsNone(value['error'],value)
        self.assertEqual(value['action_steps'],0)
        value,_=await self.cell("""np.testing.assert_allclose(pixel_to_plane(snapshot,'head',[420,240],1),point,atol=1e-12)
try:
    robo.triangulate([views[0],views[0]])
except ValueError as exc:
    assert 'Insufficient triangulation baseline' in str(exc)
else:
    raise AssertionError('Degenerate geometry must still be rejected')
""")
        self.assertIsNone(value['error'],value)
        self.assertEqual(value['action_steps'],0)
        self.assertFalse(self.submissions)

    async def test_real_protocol_persistence_output_images_and_isolation(self):
        async with Client(self.server) as client:
            result = await client.call_tool('python_cell',dict(code='x=40\ndef f(v): return v+2\nf(x)',cameras=['head']))
            self.assertFalse(result.is_error)
            value=json.loads(result.content[0].text)
            self.assertIsNone(value['error'],value)
            self.assertEqual(value['value'],'42')
        value,result = await self.cell('print(f(x)); display(robo.image("head").crop((0,0,10,10))); x+3')
        self.assertEqual(value['stdout'],'42\n'); self.assertEqual(value['value'],'43')
        self.assertEqual(sum(c.type=='image' for c in result.content),2)
        value,_ = await self.cell('import os, socket\nprint(os.path.exists("/home/zxc/文档/ChatGPT/RoboRAG"))\ns=socket.socket(); s.settimeout(.1)\ns.connect(("1.1.1.1",443))')
        self.assertIn('False',value['stdout']); self.assertIn('Network is unreachable',value['error'])
        self.assertEqual(len(self.submissions),0)

    async def test_plan_gate_and_invalid_motion_do_not_submit(self):
        result,_=await self.cell('robo.move("right", xyz=[.2,0,1], steps=4)')
        self.assertIn('record_plan',result['error']); self.assertFalse(self.submissions)
        self.memory.plan = {'steps':['test']}
        result,_=await self.cell('robo.move("right", xyz=[2,0,1], steps=1)')
        self.assertIn('translation norm',result['error']); self.assertFalse(self.submissions)
        result,_=await self.cell('robo.execute(subgoal="invalid",expected_feedback="none", actions=[[0]*14]*25)')
        self.assertIsNotNone(result['error']); self.assertFalse(self.submissions)

    async def test_tcp_turn_geometry_inactive_arm_and_error_feedback(self):
        self.memory.plan = {'steps':['test']}
        result,_=await self.cell('r=robo.move("right", quaternion=[.7071067812,0,0,.7071067812], steps=16); r["target_error"]')
        self.assertIsNone(result['error'],result)
        self.assertEqual(result['action_steps'],16)
        pose=np.asarray(self.state['action_state']['right_ee_pose'])
        r=Rotation.from_quat(pose[[4,5,6,3]])
        np.testing.assert_allclose(pose[:3]+r.apply([.145,0,0]), [.145,0,1], atol=1e-10)
        # Independent reconstruction checks every intermediate TCP, not just endpoint.
        xyz=np.array([0.,0.,1.]); rot=Rotation.identity()
        for row in self.submissions[0]['actions']:
            np.testing.assert_allclose(row[:7], [0,0,0,0,0,0,.7], atol=1e-12)
            self.assertEqual(row[13], .7)
            xyz+=row[7:10]; rot=Rotation.from_rotvec(row[10:13])*rot
            np.testing.assert_allclose(xyz+rot.apply([.145,0,0]), [.145,0,1], atol=1e-10)
        self.assertIn('orientation_rad',result['value'])

    async def test_partial_execution_stops_tail_even_if_caught(self):
        self.memory.plan = {'steps':['test']}; self.truncate=True
        result,_=await self.cell('for i in range(3):\n try: robo.move("right", xyz=[.16+i*.01,0,1],steps=4)\n except RuntimeError as e: print(e)')
        self.assertEqual(len(self.submissions),1)
        self.assertEqual(result['action_steps'],1); self.assertTrue(result['motion_stopped'])
        self.truncate=False
        result,_=await self.cell('robo.move("right",xyz=[.17,0,1],steps=4)')
        self.assertEqual(len(self.submissions),2); self.assertEqual(result['action_steps'],4)

    async def test_exception_preserves_actions_and_timeout_loses_namespace(self):
        self.memory.plan={'steps':['test']}
        result,_=await self.cell('kept=9; robo.grip("right",0,steps=2); 1/0')
        self.assertIn('ZeroDivisionError',result['error']); self.assertEqual(result['action_steps'],2)
        result,_=await self.cell('kept'); self.assertEqual(result['value'],'9')
        result,_=await self.cell('while True: pass',timeout=.15)
        self.assertTrue(result['namespace_lost'])
        result,_=await self.cell('kept')
        self.assertTrue(result['new_namespace']); self.assertIn('NameError',result['error'])

    async def test_gripper_hold_bypasses_cartesian_motion_and_preserves_other_arm(self):
        self.memory.plan={'steps':['test']}
        before=copy.deepcopy(self.state['action_state'])
        result,_=await self.cell('robo.grip("right",0,steps=5); robo.hold(steps=3)')
        self.assertIsNone(result['error'],result)
        self.assertEqual(result['action_steps'],8)
        self.assertEqual(len(self.submissions),2)
        self.assertTrue(all('joint_hold' in r and 'actions' not in r for r in self.submissions))
        self.assertEqual(self.state['action_state']['left_ee_joint_state'],[.7])
        self.assertEqual(self.state['action_state']['right_ee_joint_state'],[0])
        for side in ['left','right']:
            self.assertEqual(self.state['action_state'][side+'_ee_pose'],before[side+'_ee_pose'])
        async with Client(self.server) as client:
            invalid=await client.call_tool('hold_joints',dict(steps=True,subgoal='invalid'))
            self.assertTrue(invalid.is_error)
        self.assertEqual(len(self.submissions),2)

    async def test_last_row_tracking_failure_stops_next_motion_even_without_discard(self):
        self.memory.plan={'steps':['test']}
        submit=self.memory.submit
        async def report_error(request):
            result=await submit(request)
            result['result']['last_tracking']={'tracking_error_m':{'left':0,'right':.05}}
            return result
        self.memory.submit=report_error
        result,_=await self.cell('robo.move("right",xyz=[.16,0,1],steps=4); robo.grip("right",0)')
        self.assertEqual(len(self.submissions),1)
        self.assertEqual(result['action_steps'],4)
        self.assertTrue(result['motion_stopped'])
        self.assertIn('Motion stopped',result['error'])

    async def test_episode_end_does_not_send_motion(self):
        self.memory.plan={'steps':['test']}; self.state['episode_over']=True
        result,_=await self.cell('robo.grip("right",0)')
        self.assertFalse(self.submissions); self.assertEqual(result['action_steps'],0)
        self.assertTrue(result['motion_stopped'])


if __name__=='__main__': unittest.main()
