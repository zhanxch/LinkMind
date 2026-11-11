"""Distinct historical hands catch accidentally selecting execution-arm data."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

import h5py
import numpy as np
from scipy.spatial.transform import Rotation

from roborag.scene_registration import matrix_pose, pose_matrix, project
from roborag.scene_transfer import build_trajectory, compile_transfer, reference_observation
from tests.test_scene_transfer import fixture, action_state, camera


def distinct_fixture(path):
    fixture(path)
    with h5py.File(path, 'r+') as f:
        for group in ('state', 'action'):
            poses = f[f'{group}/right_ee_poses'][:]
            poses[:, :3] += [.35, -.2, .1]
            f[f'{group}/right_ee_poses'][:] = poses
            f[f'{group}/right_ee_joint_states'][:] = .2


class CrossArmTests(unittest.TestCase):
    def test_each_arm_reads_source_commands_but_routes_only_to_selected_hand(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'train.h5'; distinct_fixture(path)
            a = np.eye(4); a[:3, :3] = Rotation.from_euler('z', .45).as_matrix()
            a[:3, 3] = [.1, -.15, .02]
            for source, current in [('left', 'right'), ('right', 'left')]:
                with self.subTest(source=source, current=current), h5py.File(path) as f:
                    trajectory = build_trajectory(path, 0, 8, current,
                        [dict(frame=0, matrix=a)], source_arm=source)
                    start = a @ pose_matrix(f[f'state/{source}_ee_poses'][0])
                    state = action_state(matrix_pose(start)); other = source
                    state[f'{other}_ee_joint_state'] = [.37]
                    pose = start.copy()
                    for i, row in enumerate(compile_transfer(state, trajectory, 0, 8)):
                        offset = 0 if current == 'left' else 7
                        pose[:3, 3] += row[offset:offset + 3]
                        pose[:3, :3] = Rotation.from_rotvec(row[offset + 3:offset + 6]).as_matrix() @ pose[:3, :3]
                        expected = a @ pose_matrix(f[f'action/{source}_ee_poses'][i])
                        np.testing.assert_allclose(pose, expected, atol=1e-12)
                        self.assertEqual(row[offset + 6], f[f'action/{source}_ee_joint_states'][i, 0])
                        held = row[7:14] if current == 'left' else row[:7]
                        np.testing.assert_allclose(held, [0.] * 6 + [.37])
                    implicit = build_trajectory(path, 0, 8, current, [dict(frame=0, matrix=a)])
                    explicit = build_trajectory(path, 0, 8, current, [dict(frame=0, matrix=a)], source_arm=current)
                    self.assertEqual(implicit, explicit)
                    self.assertNotEqual(trajectory['poses'], implicit['poses'])
            with self.assertRaises(ValueError):
                build_trajectory(path, 0, 8, 'left', [dict(frame=0, matrix=a)], source_arm='')


class CrossArmMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_prepare_returns_cross_arm_geometry_without_dispatch(self):
        from mcp import Client
        from mcp.types import CallToolResult, TextContent
        from roborag.mcp.server import create_server
        from roborag.mcp.session import EpisodeMemory
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); train = path / 'train.h5'; distinct_fixture(train)
            (path / 'obs').mkdir()
            observation, images = reference_observation(train, 0)
            for name, raw in images.items(): (path / f'obs/{name}.png').write_bytes(raw)
            # Current right hand is already at the transformed left-hand entry.
            observation['action_state']['right_ee_pose'] = observation['action_state']['left_ee_pose']
            live = dict(step=0, episode_over=False, **observation)
            memory = EpisodeMemory(path, path, path, path, 'pack_objects_into_box', controller='delta')
            class Bank:
                def graph(self, source): return dict(source=dict(sha256='fixture', frames=9))
                def source(self, graph): return train
            memory.bank = Bank(); memory.references = {'demo:p1'}; memory.plan = {}
            memory.state = lambda: live
            memory.submit = AsyncMock(return_value=dict(result=dict(executed_rows=4)))
            memory.observation = lambda *args, **kw: CallToolResult(content=[TextContent(type='text', text=json.dumps(kw))])
            async with Client(create_server(memory)) as client:
                points = [[-.1, 0, 1], [.1, 0, 1], [0, .12, 1]]
                landmarks = [dict(reference={'head': project(camera(), p).tolist()}, current={'head': project(camera(), p).tolist()}, reference_z=1, current_z=1) for p in points]
                matched = await client.call_tool('match_scene_reference', dict(source='demo:p1', reference_frame=0, label='object', landmarks=landmarks))
                anchor = json.loads(matched.content[0].text)['anchor_id']
                args = dict(source='demo:p1', start_frame=0, end_frame=8, arm='right', knots=[dict(frame=0, anchor_id=anchor)])
                cross = await client.call_tool('prepare_motion_transfer', dict(**args, source_arm='left'))
                same = await client.call_tool('prepare_motion_transfer', args)
                self.assertFalse(cross.is_error, cross)
                self.assertFalse(same.is_error, same)
                cross, same = [json.loads(p.content[0].text) for p in (cross, same)]
                self.assertNotEqual(cross['plan_id'], same['plan_id'])
                self.assertEqual(cross['source_arm'], 'left')
                self.assertEqual(cross['arm'], 'right')
                np.testing.assert_allclose(cross['entry_target']['tcp_xyz'],[.145,0,1],atol=1e-12)
                np.testing.assert_allclose(same['entry_target']['tcp_xyz'],[.495,-.2,1.1],atol=1e-12)
                self.assertEqual(cross['first_target']['gripper'],1.)
                self.assertEqual(same['first_target']['gripper'],.2)
                memory.submit.assert_not_awaited()


if __name__ == '__main__': unittest.main()
