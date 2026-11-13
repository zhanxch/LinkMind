"""Real subprocess integration for project recipes; these are not robot benchmarks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from roborag.episode_files import write_json
from roborag.studio.projects import Projects, recipes
from roborag.studio.external_agent import process_identity

ROOT=Path(__file__).resolve().parents[1]
PYTHONPATH=str(ROOT/'src')

class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.root=self.base/'upstream';self.root.mkdir()
        self.state=self.base/'state';self.state.mkdir()
        self.projects=Projects(self.state,PYTHONPATH)
        self.script=self.root/'run.py'
        self.script.write_text('import json, os, pathlib, time\np=pathlib.Path(os.environ["LINKMIND_RUN_OUTPUT"]);p.mkdir()\nprint("ready",flush=True)\ntime.sleep(.3)\n(p/"result.json").write_text(json.dumps({"score":1,"model":"original-policy"}))\n')
        for args in [('init','-q'),('add','run.py'),('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','upstream')]:
            subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True)
        self.recipe={'argv':[sys.executable,'run.py'],'result':'result.json','metadata':{'model':'original-policy'},'timeout_seconds':10}
        self.config()
        self.project=self.projects.register(self.root)['id']
        self.projects.bind(self.project,'chat-a')

    def tearDown(self):
        self.projects.close();self.tmp.cleanup()

    def config(self):
        write_json(self.root/'linkmind.studio.json',{'version':1,'recipes':{'baseline':self.recipe}})

    def start(self,request='first'):
        return self.projects.start(self.project,'baseline',request)['id']

    def finish(self,run):
        until=time.monotonic()+12
        while time.monotonic()<until:
            value=self.projects.live(run)
            if value['status'] not in ('running','stopping'):return value
            time.sleep(.05)
        self.fail('runner did not finish')

    def test_original_program_log_result_revision_edit_and_compare(self):
        first=self.start();original=self.finish(first)
        self.assertEqual(original['status'],'completed')
        result=self.projects.follow(first)
        self.assertEqual(result['log'],'ready\n')
        self.assertEqual(result['result']['model'],'original-policy')
        self.assertEqual(self.projects.follow(first,result['next_offset'])['log'],'')
        self.script.write_text(self.script.read_text().replace('"score":1','"score":2'))
        second=self.start('modified');self.finish(second)
        compared=self.projects.compare([first,second])
        self.assertIn('source',compared['different_fields'])
        self.assertEqual([r['result']['score'] for r in compared['runs']],[1,2])
        self.assertNotEqual(original['output'],self.projects.run(second)['output'])
        self.assertIn('"score":2',(self.projects.runs/second/'source.patch').read_text())
        self.projects.close();self.projects=Projects(self.state,PYTHONPATH)
        self.assertEqual(len(self.projects.list_runs()),2)
        self.assertEqual(self.projects.follow(first)['result']['score'],1)

    def test_request_receipt_does_not_replay_and_chat_ownership(self):
        first=self.start();self.finish(first)
        self.assertEqual(self.start(),first)
        with self.assertRaisesRegex(ValueError,'different recipe'):
            self.projects.receipt(self.project,'different','first')
        with self.assertRaisesRegex(ValueError,'does not own'):
            self.projects.check('chat-b',run_id=first)
        with self.assertRaisesRegex(ValueError,'another conversation'):
            self.projects.bind(self.project,'chat-b')

    def test_missing_requirement_and_invalid_paths_block_launch(self):
        self.recipe['checks']=[{'kind':'path','value':'absent/weights'}];self.config()
        with self.assertRaisesRegex(ValueError,'Missing recipe requirements'):self.start()
        self.assertEqual(self.projects.list_runs(),[])
        for field,value in [('cameras',{'view':'../private.png'}),('result','/private.json'),('cwd','..'),('env',{'API_KEY':'value'}),('checks',None),('metadata',[])]:
            original=self.recipe.copy();self.recipe[field]=value;self.config()
            with self.assertRaises(ValueError):recipes(self.root)
            self.recipe=original

    def test_symlink_artifact_does_not_break_state_or_escape_output(self):
        run=self.start();self.finish(run)
        value=self.projects.run(run);value['recipe']['cameras']={'view':'camera.png'}
        write_json(self.projects.runs/run/'run.json',value)
        (Path(value['output'])/'camera.png').symlink_to(self.script)
        self.assertEqual(len(self.projects.list_runs()),1)
        self.assertTrue(self.projects.live(run)['artifact_errors'])
        with self.assertRaisesRegex(ValueError,'escapes'):self.projects.asset(run,'view')

    def test_stop_kills_detached_grandchild_and_retains_logs(self):
        self.script.write_text('import subprocess,sys,os,time,pathlib\np=pathlib.Path(os.environ["LINKMIND_RUN_OUTPUT"]);p.mkdir()\nc=subprocess.Popen([sys.executable,"-c","import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"],start_new_session=True)\n(p/"child").write_text(str(c.pid))\nprint("working",flush=True)\ntime.sleep(60)\n')
        run=self.start();path=Path(self.projects.run(run)['output'])/'child'
        until=time.monotonic()+5
        while not path.exists() and time.monotonic()<until:time.sleep(.05)
        pid=int(path.read_text());identity=process_identity(pid)
        ended=self.projects.stop(run)
        self.assertEqual(ended['status'],'stopped')
        self.assertNotEqual(process_identity(pid),identity)
        self.assertFalse(self.projects.busy())
        self.assertIn('working',self.projects.follow(run)['log'])

    def test_timeout_and_nonzero_exit_keep_distinct_outcomes(self):
        self.script.write_text('import time\ntime.sleep(30)\n');self.recipe['timeout_seconds']=1;self.config()
        self.assertEqual(self.finish(self.start())['status'],'timed_out')
        self.script.write_text('raise SystemExit(7)\n')
        run=self.finish(self.start('failure'))
        self.assertEqual((run['status'],run['returncode']),('failed',7))

    def test_worker_owner_loss_interrupts_program(self):
        self.script.write_text('import time\ntime.sleep(30)\n')
        run=self.start();self.projects.stop(run)
        directory=self.projects.runs/run
        (directory/'stop').unlink();(directory/'exit.json').unlink()
        p=subprocess.run([sys.executable,'-m','roborag.studio.project_worker',str(directory),str(os.getpid()),'wrong-identity'],env={**os.environ,'PYTHONPATH':PYTHONPATH},capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads((directory/'exit.json').read_text())['status'],'interrupted')

if __name__=='__main__':unittest.main()
