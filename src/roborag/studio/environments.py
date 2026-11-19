"""Profile-wide local environment bindings. Registration never imports a checkout."""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from roborag.episode_files import read_json, write_json


def template(name, marker, packages, task_dir, source):
    return dict(name=name, required=[marker], packages=packages, task_dir=task_dir, source=source)


TEMPLATES = {
    'libero': template('LIBERO', 'libero/libero/envs/env_wrapper.py', ['robosuite', 'torch', 'bddl', 'PIL', 'yaml'], 'libero/libero/bddl_files', 'Lifelong-Robot-Learning/LIBERO'),
    'libero-pro': template('LIBERO-Pro', 'perturbation.py', ['robosuite', 'torch', 'bddl', 'PIL', 'yaml'], 'libero/libero/bddl_files', 'Zxy-MLlab/LIBERO-PRO'),
    'robocasa': template('RoboCasa', 'robocasa/utils/env_utils.py', ['robosuite', 'mujoco', 'PIL'], 'robocasa/environments/kitchen', 'robocasa/robocasa'),
    'robotwin': template('RoboTwin 2', 'scripts/eval_policy_xpolicylab.py', ['sapien', 'mplib', 'PIL', 'yaml'], 'envs', 'RoboTwin-Platform/RoboTwin'),
}


def label(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', value):
        raise ValueError('Environment ID needs 1–64 letters, digits, underscores or hyphens')
    return value


def relative(value):
    if not isinstance(value, str) or not value or Path(value).is_absolute() or '..' in Path(value).parts:
        raise ValueError('Expected a checkout-relative path')
    return value


def revision(root):
    try:
        p = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=3)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


class Environments:
    def __init__(self, state):
        self.directory = Path(state) / 'environments'
        self.directory.mkdir(exist_ok=True)

    def get(self, name):
        record = read_json(self.directory / (label(name) + '.json'))
        if not record:
            raise ValueError('Register environment first: ' + name)
        return record

    def catalog(self):
        records = [read_json(p) for p in sorted(self.directory.glob('*.json'))]
        return {'templates': TEMPLATES, 'instances': [dict(r, binding=self.fingerprint(r)) for r in records]}

    def register(self, data):
        if not isinstance(data.get('root'), str) or not data['root'].strip():
            raise ValueError('Choose an environment checkout')
        root = Path(data['root']).expanduser().resolve()
        if not root.is_dir():
            raise ValueError('Environment checkout does not exist')
        kind = data.get('adapter') or 'auto'
        manifest = root / 'studio.environment.json'
        if kind == 'auto':
            if manifest.is_file():
                kind = 'custom'
            else:
                kind = next((k for k in ('libero-pro', 'libero', 'robocasa', 'robotwin')
                             if (root / TEMPLATES[k]['required'][0]).is_file()), None)
        if kind == 'custom':
            if not manifest.is_file() or manifest.stat().st_size > 65536:
                raise ValueError('Add a version 1 studio.environment.json to the environment directory')
            spec = read_json(manifest)
            if not isinstance(spec, dict) or spec.get('version') != 1:
                raise ValueError('Unsupported environment manifest')
            name = label(data.get('id') or spec.get('id'))
            entry = relative(spec.get('observe'))
            required = spec.get('required', [])
            packages = spec.get('packages', [])
            if not isinstance(required,list) or not isinstance(packages,list) or len(required)+len(packages)>100:
                raise ValueError('Invalid environment requirements')
            if any(not isinstance(p,str) or not p.isidentifier() for p in packages):
                raise ValueError('Use top-level Python import names')
            spec = dict(required=[entry, *[relative(p) for p in required]], packages=packages, observe=entry)
        elif isinstance(kind,str) and kind in TEMPLATES:
            spec = TEMPLATES[kind]
            name = label(data.get('id') or kind)
            if not (root / spec['required'][0]).is_file() or (kind == 'libero' and (root/'perturbation.py').exists()):
                raise ValueError('Adapter does not match this checkout')
        else:
            raise ValueError('Unrecognized environment. Add studio.environment.json for a custom adapter.')
        python = data.get('python') or (str(root/'.venv/bin/python') if (root/'.venv/bin/python').is_file() else sys.executable)
        # Resolving a venv interpreter symlink would silently select the system environment.
        if not isinstance(python, str) or not Path(python).expanduser().is_absolute():
            raise ValueError('Use an absolute Python executable path')
        python = os.path.abspath(os.path.expanduser(python))
        record = dict(version=1, id=name, adapter=kind, root=str(root), python=python, spec=spec)
        file = self.directory / (name + '.json')
        old = read_json(file)
        if old and old != record and data.get('replace_revision') != self.fingerprint(old):
            raise ValueError('Environment ID already registered. Choose another ID or supply its replace_revision.')
        write_json(file, record)
        return record

    @staticmethod
    def fingerprint(record):
        return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()

    def check(self, name, dependencies=True):
        rec = self.get(name)
        root = Path(rec['root'])
        interpreter = rec['python']
        checks = [{'label': 'Python', 'ready': Path(interpreter).is_file() and os.access(interpreter, os.X_OK)}]
        for p in rec['spec']['required']:
            checks.append({'label': p, 'ready': (root/p).exists()})
        default_assets = {
            'libero': ['libero/libero/assets','libero/libero/bddl_files/libero_spatial'],
            'libero-pro': ['libero/libero/assets','libero/libero/bddl_files/libero_spatial_with_mug','notebooks/custom_assets/libero_mug_yellow/libero_mug_yellow.xml'],
            'robotwin': ['env_cfg/task_config/demo_clean.yml','assets/embodiments/aloha-agilex/config.yml','assets/objects'],
            'robocasa': ['robocasa/models/assets/textures','robocasa/models/assets/fixtures','robocasa/models/assets/objects/lightwheel'],
        }
        if dependencies:
            checks.extend({'label':p,'ready':(root/p).exists()} for p in default_assets.get(rec['adapter'],[]))
        if dependencies and checks[0]['ready'] and rec['spec']['packages']:
            packages = rec['spec']['packages']
            try:
                proc = subprocess.run([interpreter, '-I', '-c',
                    'import importlib.util as u,json,sys;print(json.dumps([bool(u.find_spec(p)) for p in sys.argv[1:]]))', *packages],
                    capture_output=True, text=True, timeout=8, stdin=subprocess.DEVNULL)
                found = json.loads(proc.stdout) if proc.returncode == 0 else []
            except (OSError, ValueError, subprocess.TimeoutExpired):
                found = []
            checks.extend({'label': p, 'ready': i < len(found) and found[i] is True} for i,p in enumerate(packages))
        return dict(id=name, checks=checks, ready=all(row['ready'] for row in checks),
                    revision=revision(root), binding=self.fingerprint(rec))

    def tasks(self, name):
        record = self.get(name)
        root, kind = Path(record['root']), record['adapter']
        if kind.startswith('libero'):
            base = root / 'libero/libero/bddl_files'
            return {p.name: sorted(f.stem for f in p.glob('*.bddl')) for p in sorted(base.glob('*')) if p.is_dir()}
        if kind == 'robotwin':
            return {'tasks': sorted(p.stem for p in (root/'envs').glob('*.py') if not p.stem.startswith('_') and p.stem != 'model_utils')}
        if kind == 'robocasa':
            source = root/'robocasa/utils/dataset_registry.py'
            groups = {}
            if source.is_file():
                for node in ast.parse(source.read_text()).body:
                    if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call):
                        name = getattr(node.targets[0],'id','')
                        if name in ('ATOMIC_TASK_DATASETS','COMPOSITE_TASK_DATASETS'):
                            groups[name.split('_')[0].lower()] = [k.arg for k in node.value.keywords if k.arg]
            return groups
        return {}

    def observation(self, name, task='', suite='', seed=0):
        rec = self.get(name)
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError('Invalid seed')
        args = ['{env.python}', '{env.observe}']
        if rec['adapter'] != 'custom':
            for value in (task, suite):
                if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{0,240}', value):
                    raise ValueError('Invalid task or suite name')
            args += [rec['adapter'], '--task', task, '--suite', suite, '--seed', str(seed)]
        return dict(environment=name, argv=args, result='observation.json', cameras={'view':'view.png'},
                    timeout_seconds=180, metadata={'purpose':'environment_observation','task':task,'suite':suite,'seed':seed})

    def tokens(self, record):
        return {'{env.root}': record['root'], '{env.python}': record['python'],
                '{env.observe}': str(Path(record['root']) / record['spec']['observe'] if record['adapter']=='custom'
                                     else Path(__file__).with_name('observe_environment.py'))}
