"""Optional geometry for caller-selected held features; no sweep program or object state."""
try:
    import base_worker as base
except ModuleNotFoundError:
    from . import python_worker as base

np, Rotation = base.np, base.Rotation


class SweepRobot(base.Robot):
    def move_features(self, features, steps=16, subgoal='Move selected held features',
                      expected_feedback='Inspect tool pose, grasp and contact in current RGB'):
        """Synchronize one or both selected world features in one short dispatch.

        features maps left/right to source, target and optional quaternion/gripper.
        source must be a CURRENT visible world point selected by the caller. A
        fixed local feature offset assumes rigid grasp; it does not sense a tool.
        """
        if not isinstance(features, dict) or not features or set(features) - {'left', 'right'}:
            raise ValueError('features must map left/right to selected feature specifications')
        if type(steps) is not int or not 1 <= steps <= 24:
            raise ValueError('steps must be an integer from 1 to 24')
        snapshot, paths = self.state(), {}
        for arm, spec in features.items():
            if not isinstance(spec, dict) or set(spec) - {'source', 'target', 'quaternion', 'gripper'}:
                raise ValueError('feature specification accepts source, target, quaternion and gripper only')
            source, target = (np.asarray(spec.get(key), dtype=float) for key in ('source', 'target'))
            if any(p.shape != (3,) or not np.isfinite(p).all() for p in (source, target)):
                raise ValueError('source and target must be three finite world metres')
            start, rotation = base.tcp_pose(snapshot, arm)
            goal = rotation
            if spec.get('quaternion') is not None:
                q = np.asarray(spec['quaternion'], dtype=float)
                if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
                    raise ValueError('quaternion must be finite nonzero wxyz')
                goal = Rotation.from_quat(q[[1, 2, 3, 0]])
            gripper = spec.get('gripper')
            if gripper is not None:
                if isinstance(gripper, bool) or not isinstance(gripper, (int, float)) or not np.isfinite(gripper) or not 0 <= gripper <= 1:
                    raise ValueError('gripper must be a finite opening command in [0,1]')
                gripper = float(gripper)
            paths[arm] = dict(source=source, target=target, rotation=rotation,
                              offset=rotation.inv().apply(source-start),
                              change=(goal*rotation.inv()).as_rotvec(), gripper=gripper)
        targets = []
        for index in range(1, steps+1):
            fraction, row = index/steps, dict(steps=1)
            for arm, path in paths.items():
                rotation = Rotation.from_rotvec(path['change']*fraction)*path['rotation']
                feature = path['source'] + fraction*(path['target']-path['source'])
                row[arm] = dict(tcp_xyz=(feature-rotation.apply(path['offset'])).tolist(),
                                quaternion_wxyz=rotation.as_quat()[[3, 0, 1, 2]].tolist())
                if path['gripper'] is not None:
                    row[arm]['gripper'] = path['gripper']
            targets.append(row)
        result = self.execute(targets=targets, subgoal=subgoal, expected_feedback=expected_feedback)
        predictions = {}
        for arm, path in paths.items():
            actual, rotation = base.tcp_pose(result['current_observation'], arm)
            predicted = actual + rotation.apply(path['offset'])
            predictions[arm] = dict(xyz=predicted.tolist(), target=path['target'].tolist(),
                                    error_m=float(np.linalg.norm(predicted-path['target'])),
                                    assumption='Rigid grasp; inspect RGB, not a holding or success measurement')
        result['feature_predictions'] = predictions
        return result

    def move_feature(self, arm, source, target, quaternion=None, gripper=None, steps=16,
                     subgoal='Move a selected held feature', expected_feedback='Inspect feature and contact in RGB'):
        result = self.move_features({arm: dict(source=source, target=target, quaternion=quaternion, gripper=gripper)},
                                    steps=steps, subgoal=subgoal, expected_feedback=expected_feedback)
        result['feature_prediction'] = result['feature_predictions'][arm]
        return result


if __name__ == '__main__':
    base.Robot = SweepRobot
    base.worker_main()
