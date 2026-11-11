import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

import h5py
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

from roborag.scene_registration import (blend_transform, fit_rigid, locate_landmark,
                                        matrix_pose, pose_matrix, project)
from roborag.scene_transfer import (build_trajectory, compile_transfer,
                                    reference_observation, tcp_target)


def camera(x=0):
    t = np.diag([1., -1., -1., 1.]); t[:3, 3] = [x, 0, 2]
    return dict(intrinsics=[[100,0,32],[0,100,32],[0,0,1]], extrinsics_world=t.tolist(), size=[64,64])


def fixture(path):
    with h5py.File(path, "w") as f:
        f['additional_info/frequency'] = 25
        for arm in ('left', 'right'):
            poses=[]
            for i in range(9):
                q=Rotation.from_euler('x',i*.04).as_quat()[[3,0,1,2]]
                poses.append([i*.006,0,1,*q])
            f[f'state/{arm}_ee_poses']=poses
            f[f'action/{arm}_ee_poses']=poses[1:]+poses[-1:]
            f[f'state/{arm}_ee_joint_states']=np.ones((9,1))
            f[f'action/{arm}_ee_joint_states']=np.array([1,1,.7,.6,.6,.7,1,1,1])[:,None]
        out=io.BytesIO();Image.new('RGB',(64,64),'gray').save(out,format='JPEG')
        for short,native in [('head','cam_head'),('wrist_l','cam_left_wrist'),('wrist_r','cam_right_wrist')]:
            c=camera(0 if short=='head' else (-.2 if short=='wrist_l' else .2))
            t=np.array(c['extrinsics_world']);t[:3,:3]=t[:3,:3]@np.diag([1.,-1.,-1.])
            f[f'vision/{native}/extrinsic_matrix']=np.repeat(t[None],9,axis=0)
            f[f'vision/{native}/intrinsic_matrix']=c['intrinsics']
            f[f'vision/{native}/colors']=np.array([out.getvalue()]*9)


def action_state(pose):
    return {f'{a}_{field}':value for a in ('left','right') for field,value in
            [('ee_pose',pose),('ee_joint_state',[1.])]}


class RegistrationTests(unittest.TestCase):
    def test_known_yaw_translation_and_height_recovered_without_scale(self):
        x=np.array([[0,0,.8],[.12,0,.8],[.01,.09,.81]])
        r=Rotation.from_euler('z',.6).as_matrix();shift=np.array([.3,-.2,.04])
        fit=fit_rigid(x,x@r.T+shift)
        np.testing.assert_allclose(np.array(fit['matrix'])[:3,:3],r,atol=1e-12)
        np.testing.assert_allclose(np.array(fit['matrix'])[:3,3],shift,atol=1e-12)
        with self.assertRaises(ValueError):fit_rigid(x,2*x,max_error_m=.005)

    def test_full_3d_registration_and_degenerate_correspondence_rejection(self):
        x=np.array([[0,0,0],[.2,0,0],[0,.15,0],[0,0,.12]])
        r=Rotation.from_euler('xyz',[.2,-.3,.4]).as_matrix()
        fit=fit_rigid(x,x@r.T+[.1,.2,.8],mode='rigid')
        np.testing.assert_allclose(np.array(fit['matrix'])[:3,:3],r,atol=1e-12)
        for x in (np.zeros((3,3)), np.array([[0,0,0],[.1,0,0],[.2,0,0]])):
            with self.assertRaises(ValueError):fit_rigid(x,x,mode='rigid')

    def test_calibrated_triangulation_and_height_projection(self):
        cams={'head':camera(),'wrist_l':camera(-.2)};point=np.array([.03,.04,1.])
        pixels={name:project(c,point).tolist() for name,c in cams.items()}
        found,meta=locate_landmark(cams,pixels)
        np.testing.assert_allclose(found,point,atol=1e-12)
        self.assertEqual(meta['method'],'multi_view_triangulation')
        found,_=locate_landmark(cams,{'head':pixels['head']},plane_z=1.)
        np.testing.assert_allclose(found,point,atol=1e-12)
        with self.assertRaises(ValueError):locate_landmark(cams,{'head':pixels['head']})
        pixels['wrist_l'][1]+=20
        with self.assertRaises(ValueError):locate_landmark(cams,pixels)

    def test_no_behind_camera_outside_image_or_same_view_triangulation(self):
        cams={'a':camera(),'b':camera()}
        for points,z in [({'a':[99,2]},1),({'a':[32,32]},3),({'a':[32,32],'b':[32,32]},None)]:
            with self.assertRaises(ValueError):locate_landmark(cams,points,z)

    def test_multi_anchor_blend_retains_endpoints_and_proper_rotations(self):
        a=np.eye(4);b=np.eye(4);b[:3,:3]=Rotation.from_euler('z',1.2).as_matrix();b[:3,3]=[.3,.1,0]
        np.testing.assert_allclose(blend_transform(a,b,0),a)
        np.testing.assert_allclose(blend_transform(a,b,1),b)
        mid=blend_transform(a,b,.5)
        self.assertAlmostEqual(np.linalg.det(mid[:3,:3]),1)
        np.testing.assert_allclose(mid[:3,3],[.15,.05,0])


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'train.h5';fixture(self.path)
    def tearDown(self):self.tmp.cleanup()

    def test_train_usd_camera_conversion_and_robot_geometry(self):
        obs,_=reference_observation(self.path,0)
        np.testing.assert_allclose(obs['cameras']['head']['extrinsics_world'],camera()['extrinsics_world'])
        self.assertEqual(tcp_target([0,0,1,1,0,0,0],1)['tcp_xyz'],[.145,0,1])

    def test_every_transformed_pose_and_gripper_reached_by_native_delta_grammar(self):
        t=np.eye(4);t[:3,:3]=Rotation.from_euler('z',.7).as_matrix();t[:3,3]=[.15,-.1,.02]
        traj=build_trajectory(self.path,0,8,'left',[dict(frame=0,matrix=t)])
        start=t@pose_matrix([0,0,1,1,0,0,0]);state=action_state(matrix_pose(start))
        state['right_ee_joint_state']=[.4]
        rows=compile_transfer(state,traj,0,24)
        pose=start.copy()
        for i,row in enumerate(rows):
            pose[:3,3]+=row[:3];pose[:3,:3]=Rotation.from_rotvec(row[3:6]).as_matrix()@pose[:3,:3]
            np.testing.assert_allclose(pose,pose_matrix(traj['poses'][i]),atol=1e-12)
            self.assertEqual(row[6],traj['grippers'][i]);self.assertEqual(row[13],.4)
            np.testing.assert_allclose(row[7:13],0)

    def test_chunk_rebase_uses_measurement_and_does_not_skip_source_target(self):
        traj=build_trajectory(self.path,0,8,'right',[dict(frame=0,matrix=np.eye(4))])
        state=action_state([.004,0,1,1,0,0,0])
        rows=compile_transfer(state,traj,0,2)
        self.assertAlmostEqual(rows[0][7],.002)
        self.assertAlmostEqual(rows[1][7],.006)
        with self.assertRaises(ValueError):compile_transfer(action_state([2,0,1,1,0,0,0]),traj,0,2)
        with self.assertRaises(ValueError):compile_transfer(state,traj,0,25)

    def test_source_and_destination_anchors_can_differ(self):
        a=np.eye(4);b=np.eye(4);b[0,3]=.1
        traj=build_trajectory(self.path,0,8,'right',[dict(frame=2,matrix=a),dict(frame=5,matrix=b)])
        with h5py.File(self.path) as f:
            poses=f['action/right_ee_poses'][:8]
        np.testing.assert_allclose(traj['poses'][0],poses[0])
        self.assertAlmostEqual(traj['poses'][6][0],poses[6,0]+.1)
        with self.assertRaises(ValueError):build_trajectory(self.path,0,8,'left',[dict(frame=5,matrix=a),dict(frame=2,matrix=b)])


class MCPTransferTests(unittest.IsolatedAsyncioTestCase):
    async def test_calibration_is_read_only_and_targets_use_current_grip(self):
        from mcp import Client
        from mcp.types import CallToolResult,TextContent
        from roborag.mcp.server import create_server
        from roborag.mcp.session import EpisodeMemory
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);train=path/'train.h5';fixture(train)
            (path/'obs').mkdir()
            obs,imgs=reference_observation(train,0)
            for name,raw in imgs.items():(path/f'obs/{name}.png').write_bytes(raw)
            live=dict(step=0,episode_over=False,**obs)
            memory=EpisodeMemory(path,path,path,path,'pack_objects_into_box',controller='delta')
            class Bank:
                def graph(self,source):return dict(source=dict(sha256='fixture',frames=9))
                def source(self,graph):return train
            memory.bank=Bank();memory.references={'demo:p1'};memory.plan={};memory.state=lambda:live
            memory.submit=AsyncMock(return_value=dict(result=dict(executed_rows=4)))
            memory.observation=lambda *args,**kw:CallToolResult(content=[TextContent(type='text',text=json.dumps(kw))])
            async with Client(create_server(memory)) as client:
                tools=await client.list_tools();names={t.name for t in tools.tools}
                self.assertNotIn('execute_motion_transfer',names);self.assertNotIn('read_motion_reference',names)
                self.assertIn('execute_chunk',names)
                inspected=await client.call_tool('inspect_transfer_reference',dict(source='demo:p1',frames=[0,4]))
                self.assertFalse(inspected.is_error)
                points=[[-.1,0,1],[.1,0,1],[0,.12,1]]
                landmarks=[dict(reference={'head':project(camera(),p).tolist()},current={'head':project(camera(),p).tolist()},reference_z=1,current_z=1) for p in points]
                matched=await client.call_tool('match_scene_reference',dict(source='demo:p1',reference_frame=0,label='object',landmarks=landmarks))
                self.assertFalse(matched.is_error,matched)
                anchor=json.loads(matched.content[0].text)['anchor_id']
                prepared=await client.call_tool('prepare_motion_transfer',dict(source='demo:p1',start_frame=0,end_frame=8,arm='left',knots=[dict(frame=0,anchor_id=anchor)]))
                self.assertFalse(prepared.is_error,prepared)
                reference=json.loads(prepared.content[0].text)
                repeated=await client.call_tool('prepare_motion_transfer',dict(source='demo:p1',start_frame=0,end_frame=8,arm='left',knots=[dict(frame=0,anchor_id=anchor)]))
                self.assertEqual(reference,json.loads(repeated.content[0].text))
                memory.submit.assert_not_awaited()
                # Model chooses current timing/grip; geometry is taken from TRAIN.
                target={**reference['final_target'],'gripper':.31}
                result=await client.call_tool('execute_chunk',dict(targets=[dict(steps=4,left=target)],subgoal='use aligned target',expected_feedback='current grasp holds'))
                self.assertFalse(result.is_error,result)
                request=memory.submit.call_args.args[0]
                self.assertEqual(memory.submit.call_count,1)
                self.assertEqual(len(request['actions']),4)
                self.assertEqual([row[6] for row in request['actions']],[.31]*4)
                self.assertAlmostEqual(request['actions'][0][0],.012)
                self.assertEqual(request['action_encoding']['targets'][0]['left'],target)


if __name__ == '__main__':unittest.main()
