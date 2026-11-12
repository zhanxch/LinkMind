"""Display-only RGB snapshots; publishing never dispatches a robot action."""
from pathlib import Path
import time

from roborag.episode_files import write_json


class LiveCamera:
    def __init__(self, directory, fps=4, clock=time.monotonic, wall_clock=time.time):
        if not 0 < fps <= 10:
            raise ValueError("Camera rate must be between 0 and 10 frames per second")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.interval, self.clock, self.wall_clock = 1 / fps, clock, wall_clock
        self.last = float("-inf")
        self.frame = 0

    def attach(self, api):
        """Observe completed native steps, whether dispatched as joints or deltas."""
        take_action = api._env.take_action
        def displayed_action(*args, **kwargs):
            result = take_action(*args, **kwargs)
            api._cached_obs = None
            self.publish(api)
            return result
        api._env.take_action = displayed_action

    def publish(self, api, *, force=False):
        now = self.clock()
        if not force and now - self.last < self.interval:
            return
        self.last = now
        try:
            images = api.observe()["png"]
            cameras = [name for name in ("head", "wrist_l", "wrist_r") if name in images]
            if not cameras:
                raise ValueError("No RGB cameras are available")
            for name in cameras:
                target = self.directory / f"{name}.png"
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(images[name])
                temporary.replace(target)
            self.frame += 1
            write_json(self.directory / "frame.json", dict(frame=self.frame, captured_at=self.wall_clock(),
                       step=api.step, cameras=cameras))
            (self.directory / "error.json").unlink(missing_ok=True)
        except Exception as error:
            # A display failure must not turn an already executed action into a retry.
            try:
                write_json(self.directory / "error.json", dict(error=str(error), at=self.wall_clock()))
            except OSError:
                pass  # Disk failure also must not change control outcomes.
