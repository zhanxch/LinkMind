"""Persistent policy Python, run only inside the filesystem/network namespace.

The parent owns robot access. This worker never imports the simulator or project.
Cells can compose public observations and the existing validated motion protocol.
"""
import ast
import base64
import contextlib
import io
import json
import math
import sys
import traceback

import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

WIRE = sys.stdout
INPUT = sys.stdin


def send(value):
    WIRE.write(json.dumps(value, allow_nan=False) + '\n')
    WIRE.flush()


def rpc(method, **arguments):
    send(dict(kind='call', method=method, arguments=arguments))
    reply = json.loads(INPUT.readline())
    if 'error' in reply:
        raise RuntimeError(reply['error'])
    return reply['value']


def display(image):
    if not isinstance(image, Image.Image):
        image = Image.fromarray(np.asarray(image).astype('uint8'))
    image = image.copy()
    image.thumbnail((1280, 1280))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    send(dict(kind='display', data=base64.b64encode(buffer.getvalue()).decode()))


def ray(snapshot, camera, uv):
    c = snapshot['cameras'][camera]
    k, t = np.asarray(c['intrinsics']), np.asarray(c['extrinsics_world'])
    direction = t[:3, :3] @ np.linalg.solve(k, [*uv, 1.])
    return t[:3, 3], direction / np.linalg.norm(direction)


def pixel_to_plane(snapshot, camera, uv, z):
    """RGB ray intersected with caller-supplied world height, not measured depth."""
    origin, direction = ray(snapshot, camera, uv)
    if abs(direction[2]) < 1e-7:
        raise ValueError('Ray is parallel to plane')
    distance = (z - origin[2]) / direction[2]
    if distance <= 0:
        raise ValueError('Plane intersection is behind camera')
    return origin + distance * direction


def triangulate(views):
    """views=[(state_snapshot, camera, [u,v]), ...], same STATIC visible point.

    Returns point, ray angle and reprojection residuals. Correspondence correctness
    remains the caller's responsibility; a moving object cannot be triangulated
    from unrelated times. Calibrations stay paired with their own snapshots.
    """
    if len(views) < 2:
        raise ValueError('Supply at least two views')
    rays = [ray(s, c, uv) for s, c, uv in views]
    angle = max(math.degrees(math.acos(np.clip(abs(float(d @ e)), 0, 1)))
                for _, d in rays for _, e in rays)
    if angle < 2:
        raise ValueError('Insufficient triangulation baseline (<2 degrees)')
    projectors = [np.eye(3) - np.outer(d, d) for _, d in rays]
    point = np.linalg.solve(sum(projectors), sum(p @ o for p, (o, _) in zip(projectors, rays)))
    errors = []
    for snapshot, camera, uv in views:
        c = snapshot['cameras'][camera]
        p = np.linalg.solve(np.asarray(c['extrinsics_world']), np.r_[point, 1])[:3]
        if p[2] <= 0:
            raise ValueError('Triangulation is behind a camera')
        pixel = np.asarray(c['intrinsics']) @ p
        errors.append(float(np.linalg.norm(pixel[:2] / pixel[2] - uv)))
    return dict(xyz=point.tolist(), reprojection_error_px=errors, ray_angle_degrees=angle)


def tcp_pose(snapshot, arm):
    pose = snapshot['action_state'][f'{arm}_ee_pose']
    rot = Rotation.from_quat(np.asarray(pose[3:])[[1, 2, 3, 0]])
    return np.asarray(pose[:3]) + rot.apply([.145, 0, 0]), rot


class Robot:
    # Same pure geometry functions, with both public spellings supported.
    pixel_to_plane = staticmethod(pixel_to_plane)
    triangulate = staticmethod(triangulate)
    tcp_pose = staticmethod(tcp_pose)

    def state(self):
        """Current public state, including calibration; gripper values are commands."""
        return rpc('state')

    def image(self, camera='head'):
        """PIL image of the current public RGB (no simulation step)."""
        return Image.open(io.BytesIO(base64.b64decode(rpc('image', camera=camera)))).copy()

    def show(self, camera='head'):
        display(self.image(camera))

    def execute(self, *, subgoal, expected_feedback, actions=None, segments=None,
                targets=None, return_home=False):
        """Existing execute_chunk grammar; max 24 rows per dispatch. Returns receipt/state.

        A truncated action stops further motion in this cell, even if caught.
        Inspect the returned images and use a NEW cell to revise the action.
        """
        args = dict(subgoal=subgoal, expected_feedback=expected_feedback, cameras=[])
        args.update({k: v for k, v in dict(actions=actions, segments=segments,
                    targets=targets, return_home=return_home).items() if v is not None})
        return rpc('execute', **args)

    def move(self, arm, xyz=None, quaternion=None, gripper=None, steps=16,
             subgoal='Move to current-scene target', expected_feedback='Inspect pose and RGB'):
        """Interpolate requested TCP xyz and orientation; 1-24 steps, no automatic retry.

        xyz=None keeps the current TCP fixed through a turn. quaternion is wxyz.
        Each intermediate TCP is converted by the unchanged targets compiler.
        This does not plan collisions, choose grasps, or guarantee tracking.
        """
        if arm not in ('left', 'right') or type(steps) is not int or not 1 <= steps <= 24:
            raise ValueError('arm must be left/right and steps integer 1..24')
        state = self.state()
        start, rotation = tcp_pose(state, arm)
        end = start if xyz is None else np.asarray(xyz, dtype=float)
        if end.shape != (3,) or not np.isfinite(end).all():
            raise ValueError('xyz must be three finite metres')
        goal = rotation if quaternion is None else Rotation.from_quat(np.asarray(quaternion)[[1,2,3,0]])
        change = (goal * rotation.inv()).as_rotvec()
        targets = []
        for index in range(1, steps + 1):
            fraction = index / steps
            q = (Rotation.from_rotvec(change * fraction) * rotation).as_quat()[[3,0,1,2]]
            target = dict(tcp_xyz=(start + fraction * (end-start)).tolist(), quaternion_wxyz=q.tolist())
            if gripper is not None:
                target['gripper'] = float(gripper)
            targets.append(dict(steps=1, **{arm: target}))
        result = self.execute(targets=targets, subgoal=subgoal, expected_feedback=expected_feedback)
        actual, r = tcp_pose(result['current_observation'], arm)
        result['target_error'] = dict(tcp_m=float(np.linalg.norm(end-actual)),
                                      orientation_rad=float((goal*r.inv()).magnitude()))
        return result

    def grip(self, arm, value, steps=8):
        """Stationary gripper command; inspect RGB to establish grasp/release."""
        before = self.state()
        result = rpc('hold', arm=arm, gripper=value, steps=steps,
                     subgoal=f'{arm} gripper command {value} at measured arm joints')
        start, rotation = tcp_pose(before, arm)
        actual, measured = tcp_pose(result['current_observation'], arm)
        result['target_error'] = dict(tcp_m=float(np.linalg.norm(actual-start)),
                                     orientation_rad=float((measured*rotation.inv()).magnitude()))
        return result

    def hold(self, steps=8):
        """Hold both measured arm joint positions and existing gripper commands."""
        return rpc('hold', steps=steps, subgoal='Hold measured joints to settle')

    def home(self):
        """Existing return_home; withdraw clear of objects first."""
        return self.execute(return_home=True, subgoal='Return both arms home', expected_feedback='Home pose')


class LimitedOutput(io.StringIO):
    def write(self, text):
        remaining = 16000 - self.tell()
        if remaining > 0:
            super().write(text[:remaining])
        return len(text)


def worker_main():
    namespace = dict(robo=Robot(), np=np, math=math, Rotation=Rotation, Image=Image,
                     display=display, pixel_to_plane=pixel_to_plane, triangulate=triangulate,
                     tcp_pose=tcp_pose, __name__='__cell__')
    for line in INPUT:
        request = json.loads(line)
        output = LimitedOutput()
        error, value = None, None
        try:
            tree = ast.parse(request['code'], '<robot-cell>', 'exec')
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                if tree.body and isinstance(tree.body[-1], ast.Expr):
                    last = tree.body.pop()
                    exec(compile(tree, '<robot-cell>', 'exec'), namespace)
                    value = repr(eval(compile(ast.Expression(last.value), '<robot-cell>', 'eval'), namespace))[:8000]
                else:
                    exec(compile(tree, '<robot-cell>', 'exec'), namespace)
        except BaseException:
            error = traceback.format_exc(limit=6)[-6000:]
        send(dict(kind='done', stdout=output.getvalue(), value=value, error=error))


if __name__ == "__main__":
    worker_main()
