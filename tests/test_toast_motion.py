"""Check measured joint holds, partial rejection, and exact default behavior."""
import copy
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/RoboICL/third_party/RoboDojo'))
sys.path.insert(0,str(ROOT/'vendor/HexaShell'))
from src.eval_client.ik_continuity import IKContinuityError
from hexashell.server import geometry
from roborag.rag_execution import execute_delta_actions
from roborag.toast_motion import execute_joint_hold, execute_guarded_delta, dispatch_robot_request, enable_toast_guard


def original_sim_source(source):
    push_replacements = [('        rejection_errors = ()\n'
      '        if task.removesuffix("_random") == "push_T":\n'
      '            from src.eval_client.ik_continuity import IKContinuityError, IKContinuityGuard\n'
      '            # Native opt-in check uses robot joints and IK targets only;\n'
      '            # it rejects both arms/grippers before dispatch, without replanning.\n'
      '            env.ik_continuity_guard = IKContinuityGuard(\n'
      '                max_joint_increment_rad=.25, log_path=output / "ik-continuity.jsonl")\n'
      '            rejection_errors = (IKContinuityError,)\n',
      ''),
     ('api = LiveAPI(env, output, task_instruction=task.removesuffix("_random") == "push_T")',
      'api = LiveAPI(env, output)'),
     ('if rejection_errors or task.removesuffix', 'if task.removesuffix'),
     ('                elif "planar_measure" in request:\n'
      '                    if task.removesuffix("_random") != "push_T":\n'
      '                        raise ValueError("Planar measurements are only enabled for push_T")\n'
      '                    from roborag.planar_measurements import measure_planar\n'
      '                    result, code = measure_planar(api, args.hexashell, '
      'request["planar_measure"])\n',
      ''),
     ('                    if rejection_errors:\n'
      '                        result = (execute_delta_actions(api, request["actions"], '
      'rejection_errors=rejection_errors) if "actions" in request\n'
      '                                  else execute_chunk(api, request["chunk"]))\n'
      '                    else:\n'
      '                        result = dispatch_robot_request(api, request, task)\n',
      '                    result = dispatch_robot_request(api, request, task)\n')]
    for inserted, original in push_replacements:
        assert source.count(inserted) == 1, inserted
        source = source.replace(inserted, original)
    replacements=[
        ('from roborag.episode_budget import add_budget_argument, apply_control_budget\n',''),
        ('    add_budget_argument(parser)\n',''),
        ('        budget = apply_control_budget(env, args.control_step_limit)\n',''),
        ('            write_json(output / "ready.json", dict(step=api.step, **budget,',
         '            write_json(output / "ready.json", dict(step=api.step, step_limit=int(env.step_lim),'),
        ('    from roborag.toast_motion import enable_toast_guard, dispatch_robot_request\n',''),
        ('        enable_toast_guard(api, task, output)\n',''),
        ('                                                   task=task, layout=args.layout, seed=args.seed,\n                                                   **({"execution_guard": {"kind": "native_ik_continuity", "max_joint_increment_rad": .25}}\n                                                      if task.removesuffix("_random") in ("make_toast", "hang_mugs", "sweep_blocks", "pack_objects_into_box") else {})))',
         '                                                   task=task, layout=args.layout, seed=args.seed))'),
        ('                    result = dispatch_robot_request(api, request, task)',
         '                    result = (execute_delta_actions(api, request["actions"]) if "actions" in request\n                              else execute_chunk(api, request["chunk"]))'),
    ]
    for inserted,original in replacements:
        assert source.count(inserted)==1,inserted
        source=source.replace(inserted,original)
    return source


def delta_api(stop_at=None,reject_at=None,lag=0):
    poses={s:np.eye(4) for s in ['left','right']}
    arms={s:SimpleNamespace(ee=lambda s=s:poses[s].copy(), joints=lambda:np.zeros(6),gripper_target=.6,
          _robot=SimpleNamespace(gripper_name=s+'_gripper')) for s in poses}
    api=SimpleNamespace(step=0,over=False,arm=lambda s:arms[s],geometry=geometry,_action_log=io.StringIO())
    def take(command):
        if api.step==reject_at:
            raise IKContinuityError([dict(arm='right',passed=False,error='joint_target_jump')])
        api.step+=1
        for s in poses:
            poses[s]=geometry.pose_to_matrix(command[s+'_ee_pose'])
            poses[s][0,3]-=lag
        if api.step==stop_at:api.over=True
    api._env=SimpleNamespace(take_action=take,robot_manager=SimpleNamespace(process_name=lambda n:n+'_joint_state'))
    return api


class ToastMotionTests(unittest.TestCase):
    def test_guarded_delta_matches_original_when_no_rejection(self):
        rng=np.random.default_rng(8)
        for count in [1,8,24]:
            rows=[]
            for _ in range(count):
                row=[]
                for arm in range(2):row += [*rng.uniform(-.005,.005,3),*rng.uniform(-.03,.03,3),.6]
                rows.append(row)
            for stop_at,lag in [(None,0),(3,0),(None,.02),(None,.05)]:
                a,b=delta_api(stop_at,lag=lag),delta_api(stop_at,lag=lag)
                expected=execute_delta_actions(a,rows)
                actual=execute_guarded_delta(b,rows)
                self.assertEqual(actual,expected)
                self.assertEqual(a._action_log.getvalue(),b._action_log.getvalue())

    def test_rejected_suffix_preserves_prefix_and_gripper_commands(self):
        api=delta_api(reject_at=1)
        row=[0,0,0,0,0,0,.6,.01,0,0,0,0,0,.6]
        close=[0,0,0,0,0,0,0,.01,0,0,0,0,0,0]
        r=execute_guarded_delta(api,[row,close,row])
        self.assertEqual((r['executed_rows'],r['discarded_rows'],api.step),(1,2,1))
        self.assertFalse(r['rejection']['rejected_action_executed'])
        self.assertEqual(api.arm('right').gripper_target,.6)
        self.assertEqual(len(api._action_log.getvalue().splitlines()),1)
        api=delta_api(reject_at=0)
        with self.assertRaises(IKContinuityError):execute_delta_actions(api,[close])

    def test_hold_uses_measured_both_arms_exact_steps_and_other_gripper(self):
        arms={s:SimpleNamespace(joints=lambda i=i:np.array([i,.2,.3,.4,.5,.6]),
              joint_target=np.ones(6)*99,gripper_target=.65) for i,s in enumerate(['left','right'])}
        api=SimpleNamespace(step=10,over=False,arm=lambda s:arms[s])
        dispatched=[]
        def run(sequences):
            dispatched.append(copy.deepcopy(sequences))
            api.step+=len(sequences['left'])
        api.run=run
        r=execute_joint_hold(api,dict(arm='right',gripper=0,steps=8))
        self.assertEqual(r['action_steps'],8); self.assertEqual(r['executed_waypoints'],0)
        self.assertEqual(arms['left'].gripper_target,.65); self.assertEqual(arms['right'].gripper_target,0)
        for s in arms:
            np.testing.assert_array_equal(dispatched[0][s],np.tile(arms[s].joints(),(8,1)))
            np.testing.assert_array_equal(arms[s].joint_target,arms[s].joints())
        execute_joint_hold(api,dict(steps=3))
        self.assertEqual(api.step,21)
        self.assertEqual(arms['left'].gripper_target,.65); self.assertEqual(arms['right'].gripper_target,0)
        for request in [dict(steps=25),dict(steps=True),dict(steps=1,arm='right'),
                        dict(steps=1,arm='right',gripper=float('nan')),dict(steps=1,arm='left',gripper=2)]:
            with self.assertRaises(ValueError):execute_joint_hold(api,request)
        self.assertEqual(api.step,21)
        api.over=True
        r=execute_joint_hold(api,dict(steps=3,arm='right',gripper=1))
        self.assertEqual(r['action_steps'],0);self.assertEqual(arms['right'].gripper_target,0)

    def test_real_adapter_hold_emits_joint_commands_without_ee_ik(self):
        from types import MethodType
        from roborag.hexashell_adapter import EpisodeAPI
        arms={s:SimpleNamespace(joints=lambda i=i:np.array([i,.2,.3,.4,.5,.6]),
              joint_target=np.ones(6)*99,gripper_target=.65,
              _robot=SimpleNamespace(arm_name=s+'_arm',gripper_name=s+'_gripper'))
              for i,s in enumerate(['left','right'])}
        api=SimpleNamespace(step=0,over=False,arms=arms,arm=lambda s:arms[s],_action_log=io.StringIO())
        commands=[]
        def take_action(command):
            self.assertFalse(any('ee_pose' in key for key in command))
            commands.append(copy.deepcopy(command));api.step+=1
        api._env=SimpleNamespace(take_action=take_action,
            robot_manager=SimpleNamespace(process_name=lambda n:n+'_joint_state'))
        api.run=MethodType(EpisodeAPI.run,api)
        r=execute_joint_hold(api,dict(arm='right',gripper=.2,steps=6))
        self.assertEqual(r['action_steps'],6)
        self.assertEqual(len(api._action_log.getvalue().splitlines()),6)
        for command in commands:
            for side in ['left','right']:
                self.assertEqual(command[side+'_arm_joint_state'],arms[side].joints().tolist())
            self.assertEqual(command['left_gripper_joint_state'],[.65])
            self.assertEqual(command['right_gripper_joint_state'],[.2])

    def test_partial_native_end_counts_only_executed_hold_steps(self):
        arm=SimpleNamespace(joints=lambda:np.zeros(6),gripper_target=.5)
        api=SimpleNamespace(step=1398,over=False,arm=lambda _:arm)
        def run(_):api.step=1400;api.over=True
        api.run=run
        r=execute_joint_hold(api,dict(steps=24))
        self.assertEqual(r['action_steps'],2);self.assertTrue(r['episode_over'])

    def test_opted_in_tasks_install_guard_and_other_tasks_keep_original_functions(self):
        for task in ['make_toast','make_toast_random','hang_mugs','hang_mugs_random','fold_clothes','stack_bowls']:
            api=SimpleNamespace(_env=SimpleNamespace())
            enable_toast_guard(api,task,Path('/tmp'))
            self.assertEqual(hasattr(api._env,'ik_continuity_guard'),task.removesuffix('_random') in ('make_toast','hang_mugs'))
        with patch('roborag.toast_motion.execute_delta_actions',return_value='original') as original, \
             patch('roborag.toast_motion.execute_guarded_delta',return_value='guarded') as guarded:
            self.assertEqual(dispatch_robot_request(None,{'actions':[1]},'fold_clothes'),'original')
            original.assert_called_once_with(None,[1]);guarded.assert_not_called()
            self.assertEqual(dispatch_robot_request(None,{'actions':[1]},'make_toast_random'),'guarded')
        with self.assertRaises(ValueError):dispatch_robot_request(None,{'joint_hold':{'steps':1}},'fold_clothes')
