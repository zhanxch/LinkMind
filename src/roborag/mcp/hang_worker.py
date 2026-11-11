"""Hang-mug extensions to the unchanged isolated Python worker."""
try:
    import base_worker as base  # The sandbox mounts the original worker here.
except ModuleNotFoundError:
    from . import python_worker as base  # Local pure-function tests only.

np, Rotation = base.np, base.Rotation


class HangRobot(base.Robot):
    def measure(self, command, **arguments):
        """Same read-only measure_mug_geometry tool, using current public RGB/calibration."""
        arguments = {k: v.tolist() if isinstance(v, (np.ndarray, np.generic)) else v
                     for k, v in arguments.items()}
        return base.rpc('measure', command=command, arguments=arguments)

    def move_feature(self, arm, source, target, quaternion=None, gripper=None, steps=16,
                     subgoal='Move a measured held feature', expected_feedback='Inspect feature pose and contact in RGB'):
        """Move a selected feature along a line while interpolating the TCP orientation.

        source is its CURRENT world xyz; target is your world destination. Computes
        a fixed feature-to-TCP offset from measured robot state. Rigid grasp is an
        assumption, not a measurement: remeasure after slipping or contact.
        """
        if arm not in ('left', 'right') or type(steps) is not int or not 1 <= steps <= 24:
            raise ValueError('arm must be left/right and steps integer 1..24')
        source, target = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
        if any(p.shape != (3,) or not np.isfinite(p).all() for p in (source, target)):
            raise ValueError('source and target must be three finite world metres')
        start, rotation = base.tcp_pose(self.state(), arm)
        if quaternion is None:
            goal = rotation
        else:
            q = np.asarray(quaternion, dtype=float)
            if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
                raise ValueError('quaternion must be finite nonzero wxyz')
            goal = Rotation.from_quat(q[[1, 2, 3, 0]])
        offset = rotation.inv().apply(source - start)
        change = (goal * rotation.inv()).as_rotvec()
        targets = []
        for index in range(1, steps + 1):
            fraction = index / steps
            r = Rotation.from_rotvec(change * fraction) * rotation
            feature = source + fraction * (target - source)
            command = dict(tcp_xyz=(feature - r.apply(offset)).tolist(),
                           quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())
            if gripper is not None:
                command['gripper'] = gripper
            targets.append(dict(steps=1, **{arm: command}))
        result = self.execute(targets=targets, subgoal=subgoal, expected_feedback=expected_feedback)
        actual, measured = base.tcp_pose(result['current_observation'], arm)
        predicted = actual + measured.apply(offset)
        result['feature_prediction'] = dict(xyz=predicted.tolist(), target=target.tolist(),
                                            error_m=float(np.linalg.norm(predicted - target)),
                                            assumption='Rigid grasp; inspect RGB, not a holding or success measurement')
        return result


if __name__ == '__main__':
    base.Robot = HangRobot
    base.worker_main()
