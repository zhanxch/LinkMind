"""Real isolated cells, public-only stereo geometry, and feature motion reconstruction."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
from mcp import Client

from roborag.hang_measurements import measure_public_rgb, geometry_module
from roborag.mcp.server import create_server
from roborag.toast_motion import dispatch_robot_request, enable_toast_guard
from tests import test_python_cells as fixtures
from tests import test_toast_motion as motion_fixtures

ROOT = Path(__file__).resolve().parents[1]


def pixels(state, camera, points):
    c = state['cameras'][camera]
    k, t = np.asarray(c['intrinsics']), np.asarray(c['extrinsics_world'])
    local = (np.linalg.inv(t) @ np.c_[points, np.ones(len(points))].T).T[:, :3]
    uv = local @ k.T
    return (uv[:, :2] / uv[:, 2:]).tolist()


class HangGeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / 'obs').mkdir()
        for camera in ('head', 'wrist_l', 'wrist_r'):
            Image.new('RGB', (640, 480)).save(self.workspace / f'obs/{camera}.png')
        self.state = fixtures.synthetic_state()

    def tearDown(self):
        self.temp.cleanup()

    def measure(self, command, **arguments):
        return measure_public_rgb(self.workspace, self.state, ROOT / 'vendor/HexaShell', command, arguments)

    def test_real_peg_geometry_from_two_views_and_silhouette_edges(self):
        ends = [[.06, 0, 1], [-.06, 0, 1]]
        a, b = (pixels(self.state, c, ends) for c in ('head', 'wrist_r'))
        edges = pixels(self.state, 'head', [[x, y, 1] for x in [-.03, .03] for y in [-.006, .006]])
        result = self.measure('peg_measure', tip=a[0], root=a[1], tip2=b[0], root2=b[1], edges=edges)
        np.testing.assert_allclose(result['tip'], ends[0], atol=1e-5)
        np.testing.assert_allclose(result['root'], ends[1], atol=1e-5)
        np.testing.assert_allclose(result['axis'], [1, 0, 0], atol=1e-4)
        self.assertAlmostEqual(result['radius_m'], .006, places=4)
        self.assertGreater(result['radius_upper_m'], result['radius_m'])
        self.assertEqual(result['action_steps'], 0)
        self.assertFalse(result['physical_success_verified'])

    def test_aperture_planar_inner_boundary_and_wrong_matches(self):
        angles = np.arange(8) * np.pi / 4
        points = np.c_[.025 * np.cos(angles), .025 * np.sin(angles), np.ones(8)]
        a, b = (pixels(self.state, c, points) for c in ('head', 'wrist_r'))
        result = self.measure('aperture', rim=a, rim2=b, center=[420, 240])
        self.assertTrue(result['measurement_ok'])
        self.assertFalse(result['physical_success_verified'])
        self.assertEqual(result['action_steps'], 0)
        # Every second camera match displaced vertically must fail stereo geometry.
        with self.assertRaises(ValueError):
            self.measure('aperture', rim=a, rim2=[[u, v+30] for u, v in b], center=[420, 240])
        with self.assertRaises(ValueError):
            self.measure('aperture', rim=a, center=[420, 240])

    def test_no_depth_fallback_motion_commands_or_hidden_observation(self):
        with self.assertRaisesRegex(ValueError, 'RGB-only'):
            self.measure('surface', pixels=[420, 240])
        with self.assertRaises(ValueError):
            self.measure('peg_place', source=[0, 0, 1])
        with self.assertRaises(ValueError):
            self.measure('surface', pixels=[420, 240], z=1, path='/tmp/secret')
        precision = geometry_module(str((ROOT / 'vendor/HexaShell').resolve()), 'precision')
        actual = precision.surface
        seen = []
        def inspect(observation, arguments):
            seen.append(copy.deepcopy(observation))
            return actual(observation, arguments)
        self.state['object_ground_truth'] = {'secret': 42}
        with patch.object(precision, 'surface', side_effect=inspect):
            self.measure('surface', pixels=[420, 240], z=1)
        self.assertEqual(set(seen[0]), {'cameras', 'png'})
        self.assertNotIn('object_ground_truth', repr(seen[0]))


class HangCellTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.CellTests.asyncSetUp(self)
        self.memory.task = 'hang_mugs'
        for camera in self.state['cameras']:
            Image.new('RGB', (640, 480)).save(self.memory.workspace / f'obs/{camera}.png')
        self.server = create_server(self.memory)
        self.kernel = self.memory.python_cells

    asyncTearDown = fixtures.CellTests.asyncTearDown
    cell = fixtures.CellTests.cell

    async def test_sandbox_measurements_persist_and_consume_no_control_steps(self):
        result, _ = await self.cell("point=robo.measure('surface',pixels=[420,240],pixels2=[220,240]); point['world_mean']")
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['action_steps'], 0)
        result, _ = await self.cell("np.testing.assert_allclose(point['world_mean'],[0,0,1],atol=1e-10); robo.measure('stereo_guide',pixels=[[420,240]])")
        self.assertIsNone(result['error'], result)
        self.assertFalse(result['new_namespace'])
        self.assertFalse(self.submissions)
        async with Client(self.server) as client:
            invalid = await client.call_tool('measure_mug_geometry', dict(command='surface', arguments=dict(pixels=[420,240])))
            self.assertTrue(invalid.is_error)
        self.assertFalse(self.submissions)

    async def test_feature_turn_and_translation_follow_independent_feature_path(self):
        self.memory.plan = {'steps': ['test']}
        source, target = np.array([.2, 0, 1]), np.array([.2, .03, 1.02])
        result, _ = await self.cell("robo.move_feature('right',source=[.2,0,1],target=[.2,.03,1.02],quaternion=[.7071067812,0,0,.7071067812],steps=16)")
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['action_steps'], 16)
        # Reconstruct native link6 motion, independently of the helper's TCP formula.
        position, rotation = np.array([0.,0.,1.]), Rotation.identity()
        for i, row in enumerate(self.submissions[0]['actions'], 1):
            np.testing.assert_allclose(row[:7], [0,0,0,0,0,0,.7], atol=1e-12)
            self.assertEqual(row[13], .7)
            position += row[7:10]
            rotation = Rotation.from_rotvec(row[10:13]) * rotation
            feature = position + rotation.apply([.2,0,0])
            np.testing.assert_allclose(feature, source+(target-source)*i/16, atol=1e-10)

    async def test_turn_about_feature_leaves_feature_stationary(self):
        self.memory.plan = {'steps': ['test']}
        result, _ = await self.cell("robo.move_feature('right',[.2,0,1],[.2,0,1],quaternion=[.7071067812,0,.7071067812,0],steps=16)")
        self.assertIsNone(result['error'], result)
        position, rotation = np.array([0.,0.,1.]), Rotation.identity()
        for row in self.submissions[0]['actions']:
            position += row[7:10]
            rotation = Rotation.from_rotvec(row[10:13]) * rotation
            np.testing.assert_allclose(position+rotation.apply([.2,0,0]), [.2,0,1], atol=1e-10)

    async def test_plan_invalid_input_and_truncation_share_existing_motion_boundary(self):
        result, _ = await self.cell("robo.move_feature('right',[.2,0,1],[.21,0,1])")
        self.assertIn('record_plan', result['error'])
        self.assertFalse(self.submissions)
        self.memory.plan = {'steps': ['test']}
        for suffix in ("steps=25", "quaternion=[0,0,0,0]", "steps=True"):
            result, _ = await self.cell("robo.move_feature('right',[.2,0,1],[.21,0,1],"+suffix+")")
            self.assertIsNotNone(result['error'])
            self.assertFalse(self.submissions)
        self.truncate = True
        result, _ = await self.cell("robo.move_feature('right',[.2,0,1],[.21,0,1],steps=4); robo.grip('right',0)")
        self.assertTrue(result['motion_stopped'])
        self.assertEqual(result['action_steps'], 1)
        self.assertEqual(len(self.submissions), 1)


class HangDispatchTests(unittest.TestCase):
    def test_hang_installs_native_guard_and_preserves_accepted_delta_and_joint_hold(self):
        for task in ('hang_mugs', 'hang_mugs_random'):
            api = motion_fixtures.delta_api()
            enable_toast_guard(api, task, ROOT)
            self.assertEqual(api._env.ik_continuity_guard.limit, .25)
            rows = [[.001,0,0,0,.01,0,.6,0,.002,0,.01,0,0,.6]] * 8
            expected_api = motion_fixtures.delta_api()
            expected = motion_fixtures.execute_delta_actions(expected_api, rows)
            self.assertEqual(dispatch_robot_request(api, {'actions': rows}, task), expected)
            self.assertEqual(api._action_log.getvalue(), expected_api._action_log.getvalue())
            with patch('roborag.toast_motion.execute_joint_hold', return_value='hold') as hold:
                self.assertEqual(dispatch_robot_request(api, {'joint_hold': {'steps': 3}}, task), 'hold')
                hold.assert_called_once()

    def test_hang_rejection_preserves_executed_prefix_and_does_not_close_gripper(self):
        for task in ('hang_mugs', 'hang_mugs_random'):
            api = motion_fixtures.delta_api(reject_at=1)
            enable_toast_guard(api, task, ROOT)
            accepted = [0,0,0,0,0,0,.6,.01,0,0,0,0,0,.6]
            rejected = [0,0,0,0,0,0,0,.01,0,0,0,0,0,0]
            result = dispatch_robot_request(api, {'actions': [accepted, rejected, accepted]}, task)
            self.assertEqual((result['action_steps'], result['executed_rows'], result['discarded_rows']), (1,1,2))
            self.assertFalse(result['rejection']['rejected_action_executed'])
            self.assertEqual(api.arm('left').gripper_target, .6)
            self.assertEqual(api.arm('right').gripper_target, .6)
            self.assertEqual(len(api._action_log.getvalue().splitlines()), 1)


if __name__ == '__main__':
    unittest.main()
