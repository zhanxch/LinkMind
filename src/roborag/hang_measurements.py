"""RGB-only HexaShell geometry; no upstream manipulation programs or simulator API."""
from functools import lru_cache
import importlib.util
import math
from pathlib import Path


CAMERAS = {'head': 'cam_head', 'wrist_l': 'cam_left_wrist', 'wrist_r': 'cam_right_wrist'}
FIELDS = {
    'surface': {'pixels', 'pixels2', 'z'},
    'stereo_guide': {'pixels', 'pixels2'},
    'peg_measure': {'tip', 'tip2', 'root', 'root2', 'edges', 'edges2'},
    'aperture': {'rim', 'rim2', 'center'},
}


@lru_cache(maxsize=4)
def geometry_module(hexashell, name):
    if name not in ('precision', 'pegs'):
        raise ValueError('Unknown geometry module')
    path = Path(hexashell) / f'tasks/hang_mugs/tools/{name}/tool.py'
    spec = importlib.util.spec_from_file_location(f'roborag_hang_{name}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pixel_text(value):
    if isinstance(value, str):
        if len(value) > 4096:
            raise ValueError('Pixel list too long')
        return value
    if not isinstance(value, list) or not value or len(value) > 32:
        raise ValueError('Pixels must be [u,v], a list of pairs, or u,v;u,v text')
    pairs = [value] if len(value) == 2 and all(isinstance(v, (int, float)) for v in value) else value
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in pair):
            raise ValueError('Pixel pairs must contain two finite numbers')
    return ';'.join(','.join(str(v) for v in pair) for pair in pairs)


class ObservationOnly:
    def __init__(self, observation):
        self.observation = observation

    def observe(self):
        return self.observation


def measure_public_rgb(workspace, state, hexashell, command, arguments):
    if command not in FIELDS or not isinstance(arguments, dict):
        raise ValueError('Unknown read-only measurement')
    if set(arguments) - FIELDS[command] - {'camera', 'camera2'}:
        raise ValueError('Unsupported geometry argument')
    args = dict(camera='head', camera2='wrist_r')
    for name, value in arguments.items():
        if name in ('camera', 'camera2'):
            if value not in CAMERAS:
                raise ValueError('Unknown camera')
            args[name] = value
        elif name == 'z':
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('z must be a finite caller-supplied height')
            args[name] = value
        else:
            args[name] = pixel_text(value)
    if command == 'aperture' and not args.get('rim2'):
        raise ValueError('aperture requires matched inner-boundary rim/rim2 pixels; no depth fallback')
    required = {'surface': ('pixels',), 'stereo_guide': ('pixels',),
                'peg_measure': ('tip', 'tip2', 'root', 'root2'),
                'aperture': ('rim', 'rim2', 'center')}[command]
    if any(not args.get(name) for name in required):
        raise ValueError('Required geometry arguments: ' + ', '.join(required))
    # Construct a new capability containing ONLY public camera calibration and RGB.
    # No depth, environment, object state, reward, motion or policy workspace handle.
    observation = dict(cameras={}, png={})
    for short, native in CAMERAS.items():
        observation['cameras'][native] = state['cameras'][short]
        observation['png'][native] = (Path(workspace) / f'obs/{short}.png').read_bytes()
    if command == 'peg_measure':
        module = geometry_module(str(Path(hexashell).resolve()), 'pegs')
        try:
            result, code = module.peg_measure(ObservationOnly(observation), args)
        except module.Stop as exc:
            raise ValueError(f'{exc.failure_class}: {exc.detail}') from exc
        result.pop('peg_arg', None)
        result.pop('notes', None)  # These refer to upstream's automatic peg-place CLI.
    else:
        module = geometry_module(str(Path(hexashell).resolve()), 'precision')
        result, code = getattr(module, command)(observation, args)
    result = dict(result)
    result['measurement_ok'] = result.pop('plan_ok', code == 0)
    result['measurement_issue'] = result.pop('plan_fail_reason', None)
    result.update(action_steps=0, measured_at_step=state['step'],
                  physical_success_verified=False,
                  source='HexaShell RGB geometry; caller-selected correspondences, no task planner')
    return result
