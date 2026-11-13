"""Own one external program, its output and descendants across Studio disconnects."""
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from roborag.episode_files import write_json
from .external_agent import process_identity


def descendants(parent):
    rows={}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if fields[0]!='Z':rows[int(p.name)]=(int(fields[1]),fields[19])
        except (OSError,IndexError,ValueError):pass
    owned=set();changed=True
    while changed:
        changed=False
        for pid,(ppid,identity) in rows.items():
            if pid not in owned and (ppid==parent or ppid in owned):owned.add(pid);changed=True
    return {pid:rows[pid][1] for pid in owned}


def kill_owned(owned, sig):
    for pid,identity in owned.items():
        if process_identity(pid)==identity:
            try:os.kill(pid,sig)
            except ProcessLookupError:pass


def main():
    directory=Path(sys.argv[1]);owner=int(sys.argv[2]);identity=sys.argv[3]
    # Reparent orphaned grandchildren to this supervisor, including programs
    # that create a new session/process group of their own.
    if ctypes.CDLL(None).prctl(36,1,0,0,0)!=0:
        raise RuntimeError('Unable to supervise descendant processes')
    recipe=json.loads((directory/'run.json').read_text())
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    env=dict(os.environ)
    parent_python=env.pop('LINKMIND_INHERITED_PYTHONPATH','')
    for name in list(env):
        if name.startswith('LINKMIND_STUDIO_'):env.pop(name)
    env.pop('PYTHONPATH',None)
    if parent_python:env['PYTHONPATH']=parent_python
    env.update(recipe['env']);env['PYTHONUNBUFFERED']='1';env['LINKMIND_RUN_OUTPUT']=recipe['output']
    status='failed';error=None;code=None;started=time.monotonic();process=None
    try:
        with (directory/'runner.log').open('wb') as log:
            process=subprocess.Popen(recipe['argv'],cwd=recipe['cwd'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            while process.poll() is None:
                if stopping or (directory/'stop').exists():status='stopped';break
                if process_identity(owner)!=identity:status='interrupted';error='Studio owner exited';break
                if time.monotonic()-started>recipe['recipe'].get('timeout_seconds',5400):status='timed_out';break
                time.sleep(.1)
            else:
                status='completed' if process.returncode==0 else 'failed'
    except Exception as exc:error=str(exc)
    finally:
        owned=descendants(os.getpid())
        kill_owned(owned,signal.SIGTERM)
        until=time.monotonic()+5
        while descendants(os.getpid()) and time.monotonic()<until:
            if process:process.poll()
            time.sleep(.1)
        kill_owned({**owned,**descendants(os.getpid())},signal.SIGKILL)
        if process:
            try:code=process.wait(timeout=3)
            except subprocess.TimeoutExpired:error='Execution cleanup is incomplete';status='cleanup_failed'
        until=time.monotonic()+3
        while descendants(os.getpid()) and time.monotonic()<until:
            time.sleep(.05)
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:pass
        except ChildProcessError:pass
        remaining=descendants(os.getpid())
        if remaining:error='Execution cleanup is incomplete';status='cleanup_failed'
        write_json(directory/'exit.json',{'status':status,'returncode':code,'error':error,
                   'ended_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-started,
                   'remaining_processes':remaining})


if __name__=='__main__':main()
