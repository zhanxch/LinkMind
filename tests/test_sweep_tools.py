"""Exercise real isolated sweep cells and independently reconstruct both arm paths."""
import ast
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.spatial.transform import Rotation

from roborag.mcp.server import create_server
from roborag.toast_motion import dispatch_robot_request, enable_toast_guard
from tests import test_python_cells as fixtures
from tests import test_toast_motion as motion_fixtures


class SweepCellTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.CellTests.asyncSetUp(self)
        self.memory.task = 'sweep_blocks'
        self.server = create_server(self.memory)
        self.kernel = self.memory.python_cells

    asyncTearDown = fixtures.CellTests.asyncTearDown
    cell = fixtures.CellTests.cell
    test_persistence_images_and_real_isolation = fixtures.CellTests.test_real_protocol_persistence_output_images_and_isolation
    test_stationary_gripper_commands = fixtures.CellTests.test_gripper_hold_bypasses_cartesian_motion_and_preserves_other_arm

    async def test_two_features_share_steps_and_follow_independent_world_paths(self):
        self.memory.plan = {'steps': ['test']}
        sources = {'left': np.array([.2, 0, 1]), 'right': np.array([.25, 0, 1])}
        targets = {'left': sources['left'], 'right': np.array([.25, .04, 1.02])}
        result, _ = await self.cell("""robo.move_features({
            'left': {'source':[.2,0,1], 'target':[.2,0,1], 'quaternion':[.7071067812,0,.7071067812,0], 'gripper':.6},
            'right': {'source':[.25,0,1], 'target':[.25,.04,1.02], 'quaternion':[.8660254038,0,0,.5]}
        },steps=16)""")
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['action_steps'], 16)
        self.assertEqual(len(self.submissions), 1)
        rows = self.submissions[0]['actions']
        self.assertEqual(len(rows), 16)
        # Reconstruct link6 motion from native deltas, not the helper's TCP code.
        for arm, offset in [('left', 0), ('right', 7)]:
            position, rotation = np.array([0., 0., 1.]), Rotation.identity()
            local_point = sources[arm] - position
            for index, row in enumerate(rows, 1):
                position += row[offset:offset+3]
                rotation = Rotation.from_rotvec(row[offset+3:offset+6])*rotation
                actual_feature = position + rotation.apply(local_point)
                expected = sources[arm] + (targets[arm]-sources[arm])*index/16
                np.testing.assert_allclose(actual_feature, expected, atol=1e-10)
                self.assertEqual(row[offset+6], .6 if arm == 'left' else .7)
        value = ast.literal_eval(result['value'])
        self.assertEqual(set(value['feature_predictions']), {'left', 'right'})
        for prediction in value['feature_predictions'].values():
            self.assertLess(prediction['error_m'], 1e-10)
            self.assertIn('Rigid grasp', prediction['assumption'])

    async def test_single_feature_keeps_other_arm_and_partial_prediction_uses_actual_state(self):
        self.memory.plan = {'steps': ['test']}
        self.truncate = True
        result, _ = await self.cell("robo.move_feature('right',[.2,0,1],[.24,0,1],steps=4)")
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['action_steps'], 1)
        self.assertTrue(result['motion_stopped'])
        prediction = ast.literal_eval(result['value'])['feature_prediction']
        np.testing.assert_allclose(prediction['xyz'], [.21,0,1], atol=1e-12)
        self.assertAlmostEqual(prediction['error_m'], .03)
        for row in self.submissions[0]['actions']:
            np.testing.assert_allclose(row[:7], [0,0,0,0,0,0,.7], atol=1e-12)

    async def test_plan_and_invalid_geometry_never_dispatch(self):
        result, _ = await self.cell("robo.move_feature('right',[.2,0,1],[.21,0,1])")
        self.assertIn('record_plan', result['error'])
        self.assertFalse(self.submissions)
        self.memory.plan = {'steps': ['test']}
        codes = [
            "robo.move_features({})",
            "robo.move_feature('third',[.2,0,1],[.21,0,1])",
            "robo.move_feature('right',[float('nan'),0,1],[.21,0,1])",
            "robo.move_feature('right',[.2,0,1],[.21,0,1],quaternion=[0,0,0,0])",
            "robo.move_feature('right',[.2,0,1],[.21,0,1],gripper=2)",
            "robo.move_feature('right',[.2,0,1],[.21,0,1],steps=True)",
            "robo.move_feature('right',[.2,0,1],[.21,0,1],steps=25)",
            "robo.move_features({'right':{'source':[.2,0,1],'target':[.21,0,1],'object_id':'secret'}})",
        ]
        for code in codes:
            result, _ = await self.cell(code)
            self.assertIsNotNone(result['error'], code)
            self.assertFalse(self.submissions, code)

    async def test_truncation_blocks_later_motion_even_if_caught(self):
        self.memory.plan = {'steps': ['test']}
        self.truncate = True
        result, _ = await self.cell("""robo.move_features({'right':{'source':[.2,0,1],'target':[.24,0,1]}},steps=4)
try:
    robo.grip('left',0)
except RuntimeError as exc:
    print(exc)
""")
        self.assertTrue(result['motion_stopped'])
        self.assertEqual(result['action_steps'], 1)
        self.assertEqual(len(self.submissions), 1)
        self.assertIn('Motion stopped', result['stdout'])
        self.assertEqual(self.state['action_state']['left_ee_joint_state'], [.7])


class SweepDispatchTests(unittest.TestCase):
    def test_guarded_acceptance_and_rejection_use_existing_native_boundary(self):
        for task in ('sweep_blocks', 'sweep_blocks_random'):
            api = motion_fixtures.delta_api()
            enable_toast_guard(api, task, Path('/tmp'))
            self.assertEqual(api._env.ik_continuity_guard.limit, .25)
            rows = [[.001,0,0,0,.01,0,.6,0,.002,0,.01,0,0,.6]]*8
            original = motion_fixtures.delta_api()
            expected = motion_fixtures.execute_delta_actions(original, rows)
            self.assertEqual(dispatch_robot_request(api, {'actions': rows}, task), expected)
            self.assertEqual(api._action_log.getvalue(), original._action_log.getvalue())
            api = motion_fixtures.delta_api(reject_at=1)
            enable_toast_guard(api, task, Path('/tmp'))
            accepted = [0,0,0,0,0,0,.6,.01,0,0,0,0,0,.6]
            rejected = [0,0,0,0,0,0,0,.01,0,0,0,0,0,0]
            receipt = dispatch_robot_request(api, {'actions':[accepted,rejected,accepted]}, task)
            self.assertEqual((receipt['action_steps'],receipt['discarded_rows']), (1,2))
            self.assertFalse(receipt['rejection']['rejected_action_executed'])
            self.assertEqual(api.arm('left').gripper_target, .6)
            self.assertEqual(api.arm('right').gripper_target, .6)
            with patch('roborag.toast_motion.execute_joint_hold', return_value='held') as hold:
                self.assertEqual(dispatch_robot_request(api, {'joint_hold':{'steps':4}}, task), 'held')
                hold.assert_called_once()


if __name__ == '__main__':
    unittest.main()
