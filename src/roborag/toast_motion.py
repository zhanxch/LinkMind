"""Opt-in native motion reliability; no object state or task planner.

Toast, hang_mugs, sweep_blocks and pack_objects_into_box opt in; other tasks keep the original dispatcher. The guard is the existing
native pre-dispatch check; gripper holds command measured joints without IK.
"""
import math

from .rag_execution import execute_chunk, execute_delta_actions, validate_delta_actions


def enable_toast_guard(api, task, output):
    if task.removesuffix('_random') not in ('make_toast', 'hang_mugs', 'sweep_blocks', 'pack_objects_into_box'):
        return
    from src.eval_client.ik_continuity import IKContinuityGuard
    api._env.ik_continuity_guard = IKContinuityGuard(
        max_joint_increment_rad=.25, log_path=output/'ik-continuity.jsonl')


def validate_joint_hold(request):
    if not isinstance(request, dict) or set(request)-{'arm','gripper','steps'}:
        raise ValueError('joint_hold expects arm, gripper and steps only')
    arm, value, steps = request.get('arm'), request.get('gripper'), request.get('steps')
    if type(steps) is not int or not 1 <= steps <= 24:
        raise ValueError('joint_hold steps must be an integer from 1 to 24')
    if arm is None and value is None:
        return
    if arm not in ('left','right') or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('A gripper command needs left/right arm and finite opening in [0,1]')


def execute_joint_hold(api, request):
    import numpy as np
    validate_joint_hold(request)
    before=api.step
    if api.over:
        return dict(action_space='measured-joint-hold',action_steps=0,executed_waypoints=0,
                    step=api.step,episode_over=True)
    # Snapshot both measured arms once. No IK and no cached Cartesian target.
    joints={side:api.arm(side).joints().copy() for side in ('left','right')}
    for side in joints:
        api.arm(side).joint_target=joints[side].copy()
    if request.get('arm') is not None:
        api.arm(request['arm']).gripper_target=float(request['gripper'])
    api.run({side:np.tile(q,(request['steps'],1)) for side,q in joints.items()})
    return dict(action_space='measured-joint-hold',submitted_steps=request['steps'],
                action_steps=api.step-before,executed_waypoints=0,step=api.step,
                episode_over=api.over,held_joint_targets={s:q.tolist() for s,q in joints.items()},
                joint_tracking_error_rad={s:float(np.max(abs(api.arm(s).joints()-q))) for s,q in joints.items()})


def execute_guarded_delta(api, actions):
    """Original delta arithmetic with an explicit receipt for rejected suffixes."""
    import json
    import numpy as np
    from scipy.spatial.transform import Rotation
    from src.eval_client.ik_continuity import IKContinuityError
    validate_delta_actions(actions)
    before, receipts = api.step, []
    rejected, last_command = None, None
    targets = {side:api.arm(side).ee().copy() for side in ('left','right')}
    for row in actions:
        if api.over:
            break
        command = {}
        for side, offset in (('left',0),('right',7)):
            targets[side][:3,3] += row[offset:offset+3]
            targets[side][:3,:3] = Rotation.from_rotvec(row[offset+3:offset+6]).as_matrix() @ targets[side][:3,:3]
            command[f'{side}_ee_pose'] = api.geometry.matrix_to_pose(targets[side])
            key=api._env.robot_manager.process_name(api.arm(side)._robot.gripper_name)
            command[key]=[row[offset+6]]
        try:
            api._env.take_action(command)
        except IKContinuityError as exc:
            rejected=exc.event
            break
        last_command=command
        api._cached_obs=None
        error={}
        for side, offset in (('left',0),('right',7)):
            arm=api.arm(side)
            arm.joint_target=arm.joints().copy()
            arm.gripper_target=row[offset+6]
            error[side]=float(np.linalg.norm(arm.ee()[:3,3]-targets[side][:3,3]))
        api._action_log.write(json.dumps(dict(step=api.step,delta_row=row,command=command,tracking_error_m=error))+'\n')
        api._action_log.flush()
        receipts.append(dict(step=api.step,tracking_error_m=error))
        if max(error.values())>.04:
            break
    return dict(action_space='dual-arx-x5/link6/ee_delta/world/m/rotvec-rad/25hz',
                submitted_rows=len(actions),executed_rows=len(receipts),executed_waypoints=0,
                action_steps=api.step-before,discarded_rows=len(actions)-len(receipts),
                last_command=last_command,last_tracking=receipts[-1] if receipts else None,
                step=api.step,episode_over=api.over,
                **({'rejection':rejected} if rejected is not None else {}))


def dispatch_robot_request(api, request, task):
    toast=task.removesuffix('_random')=='make_toast'
    guarded=toast or task.removesuffix('_random') in ('hang_mugs', 'sweep_blocks', 'pack_objects_into_box')
    if 'joint_hold' in request:
        if not guarded:
            raise ValueError('joint_hold is enabled only for make_toast, hang_mugs, sweep_blocks and pack_objects_into_box')
        return execute_joint_hold(api,request['joint_hold'])
    if 'actions' in request:
        return (execute_guarded_delta if guarded else execute_delta_actions)(api,request['actions'])
    return execute_chunk(api,request['chunk'])
