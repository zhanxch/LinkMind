"""Project-owned recipes and durable runs for external embodied repositories."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from roborag.episode_files import write_json
from .external_agent import process_identity

RECIPE_FILE = 'linkmind.studio.json'
ID = re.compile(r'^[a-zA-Z0-9_-]{1,80}$')
SECRET = re.compile(r'(token|secret|password|credential|api.?key)', re.I)


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def stamp():
    return datetime.now(timezone.utc).isoformat()


def key(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('Invalid project/run/recipe identifier')
    return value


def beneath(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path escapes the declared directory')
    return path


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=20)
    if result.returncode:
        raise ValueError('Git inspection failed: ' + result.stderr.decode(errors='replace')[:500])
    return result.stdout


def source(root, destination=None):
    if not shutil.which('git'):
        return {'git': False, 'note': 'Git is unavailable; source revision is not captured.'}
    try:
        head = git(root, 'rev-parse', 'HEAD').decode().strip()
    except ValueError:
        return {'git': False, 'note': 'No committed Git revision; this run cannot establish an original baseline.'}
    # Exact working-tree patch plus hashes of untracked inputs. Ignored datasets
    # and credentials are never copied into the run's source record.
    patch = git(root, 'diff', '--binary', 'HEAD', '--', '.')
    untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
    inputs = {}
    for name in filter(None, untracked):
        p = root / name
        if p.is_file() and not p.is_symlink() and not SECRET.search(name) and not p.name.startswith('.env'):
            inputs[name] = hashlib.sha256(p.read_bytes()).hexdigest() if p.stat().st_size <= 8*1024*1024 else 'large-file-not-hashed'
    value = {'git': True, 'commit': head, 'patch_sha256': hashlib.sha256(patch).hexdigest(),
             'dirty': bool(patch or inputs), 'untracked_sha256': inputs,
             'note': 'HEAD and tracked diff are recorded; untracked files are hashed, ignored assets and the environment are not archived.'}
    if destination:
        (destination / 'source.patch').write_bytes(patch)
        write_json(destination / 'source.json', value)
    return value


def recipes(root):
    p = root / RECIPE_FILE
    if not p.is_file():
        return {}
    if p.stat().st_size > 256*1024:
        raise ValueError('Project configuration is too large')
    return validate_recipes(root, read(p))


def validate_recipes(root, data):
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('recipes'), dict):
        raise ValueError('Expected linkmind.studio.json with version 1 and a recipes object')
    for name, recipe in data['recipes'].items():
        key(name)
        if not isinstance(recipe, dict):
            raise ValueError('Each recipe must be an object')
        argv = recipe.get('argv')
        if not isinstance(argv, list) or not argv or len(argv) > 200 or any(not isinstance(x, str) or '\0' in x or len(x)>8192 for x in argv):
            raise ValueError('Recipe argv must be a nonempty argument array, not a shell command string')
        cwd = recipe.get('cwd', '.')
        if not isinstance(cwd, str) or Path(cwd).is_absolute():
            raise ValueError('Recipe cwd must be a project-relative directory')
        beneath(root, cwd)
        env = recipe.get('env', {})
        if not isinstance(env, dict) or any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k) or SECRET.search(k) or not isinstance(v,str) or '\0' in v for k,v in env.items()):
            raise ValueError('Recipe env must contain plain strings; keep credentials in the existing provider environment')
        seconds = recipe.get('timeout_seconds', 5400)
        if type(seconds) is not int or not 1 <= seconds <= 86400:
            raise ValueError('timeout_seconds must be 1–86400')
        if not isinstance(recipe.get('checks', []), list):
            raise ValueError('checks must be an array')
        if not isinstance(recipe.get('metadata', {}), dict):
            raise ValueError('metadata must be an object')
        for check in recipe.get('checks', []):
            if not isinstance(check,dict) or check.get('kind') not in ('path','executable') or not isinstance(check.get('value'),str):
                raise ValueError('Checks need kind path/executable and a value')
        cameras = recipe.get('cameras', {})
        if not isinstance(cameras,dict) or len(cameras)>8:
            raise ValueError('cameras must be an object with at most eight output-relative paths')
        for name, path in cameras.items():
            key(name)
            if not isinstance(path,str) or Path(path).is_absolute() or '..' in Path(path).parts:
                raise ValueError('Camera paths must be relative to this run output')
        result = recipe.get('result')
        if result is not None and (not isinstance(result,str) or Path(result).is_absolute() or '..' in Path(result).parts):
            raise ValueError('Result path must be relative to this run output')
    return data['recipes']


def expand(value, root, output):
    return value.replace('{project}', str(root)).replace('{output}', str(output))


class Projects:
    def __init__(self, state, python_path):
        self.state, self.python_path = Path(state), python_path
        self.directory = self.state / 'projects'
        self.runs = self.state / 'project-runs'
        self.directory.mkdir(exist_ok=True)
        self.runs.mkdir(exist_ok=True)
        self.children = {}

    def register(self, path):
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError('Open or clone the repository into a local directory first')
        project = {'id': uuid.uuid4().hex[:16], 'path': str(root), 'name': root.name,
                   'created_at': stamp(), 'session_id': None}
        recipes(root)  # reject broken configuration before advertising it
        write_json(self.directory / (project['id']+'.json'), project)
        return {**project, 'inspection': self.inspect(project['id'])}

    def project(self, project_id):
        p = read(self.directory / (key(project_id)+'.json'))
        if not p:
            raise ValueError('Project is not registered in this conversation; use open_project')
        return p

    def bind(self, project_id, session):
        project = self.project(project_id)
        if project.get('session_id') not in (None, key(session)):
            raise ValueError('Project registration belongs to another conversation')
        project['session_id'] = session
        write_json(self.directory / (project_id+'.json'), project)
        return project

    def check(self, session, project_id=None, run_id=None):
        project = self.project(self.run(run_id)['project_id'] if run_id else project_id)
        if project['session_id'] != key(session):
            raise ValueError('This conversation does not own that project registration')
        return {'allowed': True}

    def open_workspace(self, path, session):
        """Discover a selected DSH directory, including a broken/absent config."""
        root = Path(path).expanduser().resolve()
        key(session)
        if not root.is_dir():
            raise ValueError('Workspace directory does not exist')
        project = next((p for file in self.directory.glob('*.json')
                        if (p := read(file))['path'] == str(root) and p['session_id'] == session), None)
        if project is None:
            project = {'id': uuid.uuid4().hex[:16], 'path': str(root), 'name': root.name,
                       'created_at': stamp(), 'session_id': session}
            write_json(self.directory / (project['id']+'.json'), project)
        configuration = self.configuration(project['id'])
        inspection = {}
        try:
            inspection = self.inspect(project['id'])
        except (ValueError, OSError) as exc:
            configuration['error'] = str(exc)
        return {**project, **inspection, 'configuration': configuration,
                'active_runs': [r['id'] for r in self.list_runs()
                                if r['project_path'] == str(root) and r['status'] in ('starting','running','stopping')]}

    def configuration(self, project_id):
        root = Path(self.project(project_id)['path'])
        path = beneath(root, RECIPE_FILE)
        if not path.exists():
            return {'exists': False, 'content': '{"version": 1, "recipes": {}}\n',
                    'revision': 'missing', 'error': None}
        if path.stat().st_size > 256*1024:
            raise ValueError('Project configuration is too large')
        raw = path.read_bytes()
        return {'exists': True, 'content': raw.decode('utf-8'),
                'revision': hashlib.sha256(raw).hexdigest(), 'error': None}

    def save_configuration(self, project_id, content, revision):
        root = Path(self.project(project_id)['path'])
        if any(r['project_path'] == str(root) and r['status'] in ('starting','running','stopping')
               for r in self.list_runs()):
            raise ValueError('Stop this project before editing its run configurations')
        if not isinstance(content, str) or len(content.encode()) > 256*1024:
            raise ValueError('Configuration must be UTF-8 JSON up to 256 KiB')
        validate_recipes(root, json.loads(content))
        current = self.configuration(project_id)
        if revision != current['revision']:
            raise ValueError('Configuration changed on disk; reload it before saving. Your draft has not been saved.')
        path = root / RECIPE_FILE
        temporary = root / ('.linkmind-config-'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                stream.write(content)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return self.configuration(project_id)

    def inspect(self, project_id):
        project = self.project(project_id)
        root = Path(project['path'])
        configured = recipes(root)
        checks = {}
        for name, recipe in configured.items():
            env = {**os.environ, **{k:expand(v,root,root) for k,v in recipe.get('env', {}).items()}}
            rows = []
            for check in recipe.get('checks', []):
                value = expand(check['value'], root, root)
                ok = (Path(value) if Path(value).is_absolute() else root/value).exists() if check['kind']=='path' else bool(shutil.which(value, path=env.get('PATH')))
                rows.append({'label': check.get('label', check['value']), 'ready': ok})
            executable = expand(recipe['argv'][0], root, root)
            cwd = beneath(root, recipe.get('cwd', '.'))
            resolved = str(cwd/executable) if '/' in executable and not Path(executable).is_absolute() else executable
            rows.append({'label': 'Launch executable', 'ready': bool(shutil.which(resolved, path=env.get('PATH')))})
            rows.append({'label': 'Working directory', 'ready': cwd.is_dir()})
            checks[name] = {'ready': all(r['ready'] for r in rows), 'checks': rows}
        return {**project, 'config_file': str(root/RECIPE_FILE), 'recipes': configured, 'checks': checks,
                'source': source(root), 'entry_files': [p.name for p in root.iterdir() if p.is_file() and (p.name.lower().startswith('readme') or p.name in ('pyproject.toml','requirements.txt','environment.yml','Dockerfile','package.json',RECIPE_FILE))],
                'guidance': 'Use DSH file/shell tools to read instructions, prepare the environment and edit code. Save verified argv and requirements in linkmind.studio.json; inspection checks paths, not a successful reproduction.'}

    def run(self, run_id):
        value = read(self.runs/key(run_id)/'run.json')
        if value is None:
            raise ValueError('Project run does not exist')
        return value

    def exists(self, run_id):
        return bool(ID.fullmatch(str(run_id))) and (self.runs/run_id/'run.json').is_file()

    def live(self, run_id):
        value = self.run(run_id)
        child = self.children.get(run_id)
        if child is not None and child.poll() is not None:
            self.children.pop(run_id, None)
        directory = self.runs/run_id
        exit_record = read(directory/'exit.json')
        if exit_record:
            value.update(exit_record)
        elif not value.get('pid_identity') and (datetime.now(timezone.utc)-datetime.fromisoformat(value['created_at'])).total_seconds()<10:
            value['status'] = 'starting'
        elif not value.get('pid_identity') or process_identity(value.get('pid',0)) != value.get('pid_identity'):
            value['status'] = 'interrupted'
            value['error'] = 'Supervisor exited without a final receipt; outcome is unknown.'
        else:
            value['status'] = 'stopping' if (directory/'stop').exists() else 'running'
        output = directory/'output'
        camera = []
        value['artifact_errors'] = []
        for name, relative in value['recipe'].get('cameras',{}).items():
            try:
                p = beneath(output, relative)
                if p.is_file():
                    stat = p.stat()
                    camera.append({'id':name, 'frame':stat.st_mtime_ns, 'captured_at':stat.st_mtime})
            except (ValueError, OSError) as exc:
                value['artifact_errors'].append(f'{name}: {exc}')
        value['cameras'] = camera
        if camera:
            value['camera'] = {'frame':max(c['frame'] for c in camera), 'captured_at':max(c['captured_at'] for c in camera)}
        result_path = value['recipe'].get('result')
        try:
            value['result_available'] = bool(result_path and beneath(output,result_path).is_file())
        except (ValueError, OSError) as exc:
            value['result_available'] = False
            value['artifact_errors'].append(f'result: {exc}')
        value['log_bytes'] = (directory/'runner.log').stat().st_size if (directory/'runner.log').exists() else 0
        value['task_snapshot'] = {'session_id':value['session_id']}
        return value

    def list_runs(self):
        return sorted((self.live(p.parent.name) for p in self.runs.glob('*/run.json')), key=lambda x:x['created_at'], reverse=True)

    def busy(self):
        return any(r['status'] in ('starting','running','stopping') or any(
            process_identity(int(pid)) == identity for pid, identity in r.get('remaining_processes', {}).items()
        ) for r in self.list_runs())

    def receipt(self, project_id, recipe_id, request_id):
        key(request_id)
        for p in self.runs.glob('*/run.json'):
            r = read(p)
            if r.get('project_id') == project_id and r.get('request_id') == request_id:
                if r['recipe_id'] != recipe_id:
                    raise ValueError('Request identity was already used for a different recipe')
                return self.live(r['id'])
        return None

    def start(self, project_id, recipe_id, request_id):
        previous = self.receipt(project_id, recipe_id, request_id)
        if previous:
            return previous
        project = self.project(project_id)
        if not project['session_id']:
            raise ValueError('Bind this project to the DSH conversation before running')
        inspection = self.inspect(project_id)
        recipe = inspection['recipes'].get(key(recipe_id))
        if not recipe:
            raise ValueError('Recipe does not exist; save it in linkmind.studio.json first')
        if not inspection['checks'][recipe_id]['ready']:
            raise ValueError('Missing recipe requirements: '+json.dumps(inspection['checks'][recipe_id]['checks']))
        root = Path(project['path'])
        run_id = uuid.uuid4().hex[:16]
        directory = self.runs/run_id
        directory.mkdir()
        output = directory/'output'
        # The runner owns creation of its output directory: many upstream tools
        # deliberately refuse an existing output path.
        value = {'id':run_id, 'kind':'project', 'project_id':project_id, 'project_name':project['name'],
                 'project_path':str(root), 'session_id':project['session_id'], 'recipe_id':recipe_id, 'request_id':request_id,
                 'recipe':recipe, 'created_at':stamp(), 'status':'starting', 'output':str(output),
                 'source':source(root,directory), 'argv':[expand(x,root,output) for x in recipe['argv']],
                 'cwd':str(beneath(root,recipe.get('cwd','.'))),
                 'env':{k:expand(v,root,output) for k,v in recipe.get('env',{}).items()},
                 'result_note':'Process completion is not task success. Read the original result; human intervention must be reported separately.'}
        write_json(directory/'run.json',value)
        env = {**os.environ, 'PYTHONPATH':self.python_path}
        try:
            with (directory/'supervisor.log').open('ab') as log:
                process = subprocess.Popen([sys.executable,'-m','roborag.studio.project_worker',str(directory),str(os.getpid()),process_identity(os.getpid())],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        except OSError as exc:
            write_json(directory/'exit.json', {'status':'failed', 'error':str(exc), 'ended_at':stamp(), 'returncode':None})
            return self.live(run_id)
        value.update(pid=process.pid,pid_identity=process_identity(process.pid))
        write_json(directory/'run.json',value)
        self.children[run_id]=process
        return value

    def stop(self, run_id):
        value = self.live(run_id)
        if value['status'] not in ('starting','running','stopping'):
            return value
        (self.runs/run_id/'stop').touch()
        for _ in range(100):
            value = self.live(run_id)
            if value['status'] not in ('starting','running','stopping'):
                return value
            time.sleep(.1)
        return value

    def follow(self, run_id, offset=0, wait_seconds=0):
        if type(offset) is not int or offset<0 or not 0<=wait_seconds<=5:
            raise ValueError('Use a nonnegative byte offset and wait_seconds 0–5')
        value=self.live(run_id)
        if wait_seconds and value['status'] in ('starting','running','stopping'):
            time.sleep(wait_seconds)
            value=self.live(run_id)
        path=self.runs/run_id/'runner.log'
        chunk=b''
        if path.exists():
            with path.open('rb') as f:
                f.seek(min(offset,path.stat().st_size));offset=f.tell();chunk=f.read(16384)
        result=None
        if value['result_available'] and value['status'] not in ('starting','running','stopping'):
            p=beneath(self.runs/run_id/'output',value['recipe']['result'])
            if p.stat().st_size<=128*1024:
                try:result=read(p)
                except (ValueError,UnicodeError):result={'note':'Result is not JSON; inspect the original file at '+str(p)}
        return {'run':value,'log':chunk.decode(errors='replace'),'next_offset':offset+len(chunk),'result':result}

    def asset(self, run_id, name):
        value=self.run(run_id)
        cameras=value['recipe'].get('cameras',{})
        if name not in cameras:
            raise ValueError('Camera is not declared by this recipe')
        p=beneath(self.runs/run_id/'output',cameras[name])
        if p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or not p.is_file():
            raise ValueError('Camera image is not available')
        return p

    def compare(self, run_ids):
        if len(run_ids)!=2 or run_ids[0]==run_ids[1]:
            raise ValueError('Select two distinct runs')
        records = [self.follow(i) for i in run_ids]
        left,right=(r['run'] for r in records)
        fields=['project_path','recipe_id','recipe','source','status','returncode']
        return {'runs':records,
                'different_fields':[k for k in fields if left.get(k)!=right.get(k)],
                'note':'Raw records only. Check scenario, model, budgets and source differences before comparing metrics; no automatic success-rate claim.'}

    def close(self):
        for r in self.list_runs():
            if r['status'] in ('starting','running','stopping'):
                self.stop(r['id'])
        for p in self.children.values():
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
