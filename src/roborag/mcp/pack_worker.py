"""Persistent public reference values; motion stays on the existing robot API."""
try:
    import base_worker as base
except ModuleNotFoundError:
    from . import python_worker as base


class PackRobot(base.Robot):
    def inspect_reference(self, source, frames, cameras=None, measure_support=False):
        return base.rpc('inspect_transfer_reference', source=source, frames=frames,
                        cameras=['head'] if cameras is None else cameras,
                        measure_support=measure_support)

    def match_reference(self, source, reference_frame, label, landmarks,
                        mode='planar', max_error_m=.02):
        return base.rpc('match_scene_reference', source=source, reference_frame=reference_frame,
                        label=label, landmarks=landmarks, mode=mode, max_error_m=max_error_m)

    def prepare_reference(self, source, start_frame, end_frame, arm, knots, source_arm=None):
        return base.rpc('prepare_motion_transfer', source=source, start_frame=start_frame,
                        end_frame=end_frame, arm=arm, knots=knots, source_arm=source_arm)


if __name__ == '__main__':
    base.Robot = PackRobot
    base.worker_main()
