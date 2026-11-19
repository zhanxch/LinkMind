"""Project-run, cross-session, and manifest contracts using a real isolated worker."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from roborag.studio import observe_environment
from roborag.studio.projects import Projects
from roborag.studio.rsi_board import board, log_round

ROOT=Path(__file__).resolve().parents[1]
PYTHONPATH=str(ROOT/'src')


class RSIStudioTest(unittest.TestCase):
    def test_custom_environment_run_and_round_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project, env, state = (base/n for n in ('policy','sim','state'))
            for path in (project,env,state): path.mkdir()
            (env/'studio.environment.json').write_text(json.dumps(dict(version=1,id='tiny',observe='reset.py')))
            (env/'reset.py').write_text("from pathlib import Path\nimport os,json\np=Path(os.environ['LINKMIND_RUN_OUTPUT']);p.mkdir()\n(p/'observation.json').write_text(json.dumps({'native':{'score':0}}))\n")
            manager = Projects(state,PYTHONPATH)
            self.addCleanup(manager.close)
            registry = manager.environments
            instance = registry.register(dict(root=str(env),python=sys.executable))
            self.assertEqual(instance,registry.register(dict(root=str(env),python=sys.executable)))
            with self.assertRaisesRegex(ValueError,'already registered'):
                registry.register(dict(root=str(env),python='/missing/python'))
            revision = registry.catalog()['instances'][0]['binding']
            updated = registry.register(dict(root=str(env),python='/missing/python',replace_revision=revision))
            with self.assertRaisesRegex(ValueError, 'already registered'):
                registry.register(dict(root=str(env),python=sys.executable,replace_revision=revision))
            registry.register(dict(root=str(env),python=sys.executable,replace_revision=registry.fingerprint(updated)))
            recipe = registry.observation('tiny')
            recipe['checks'] = [{'kind':'path','value':'{env.root}/reset.py'}]
            recipe['rsi'] = dict(series='pilot',protocol='seed0',id='r0',change='baseline')
            def save():
                (project/'linkmind.studio.json').write_text(json.dumps({'version':1,'recipes':{'try':recipe}}))
            save()
            reg=manager.open_workspace(project,'chat1')
            first=manager.start(reg['id'],'try','request-1')
            until=time.monotonic()+10
            while not (manager.runs/first['id']/'exit.json').exists() and time.monotonic()<until:time.sleep(.02)
            self.assertEqual(manager.live(first['id'])['status'],'completed')
            second=manager.open_workspace(project,'chat2')
            rows=board(manager,second['id'])['rounds']
            self.assertEqual(rows[0]['metrics']['native.score'],0)
            self.assertEqual(rows[0]['environment'],'tiny')
            self.assertEqual(rows[0]['run_id'],first['id'])
            self.assertTrue(rows[0]['metrics']['elapsed_seconds']>0)
            recipe['rsi_events']='rounds.jsonl'
            recipe['rsi']['id']='unused'
            fields=dict(series='e',protocol='seed1',id='base',metrics={'reward':0})
            log_round(project/'studio.rsi.jsonl',**fields)
            log_round(project/'studio.rsi.jsonl',**dict(fields,id='child',parent='base',change='updated policy',metrics={'reward':-1}))
            log_round(project/'studio.rsi.jsonl',**dict(fields,protocol='seed2'))
            with (project/'studio.rsi.jsonl').open('a') as f:f.write('broken\n')
            view=board(manager,reg['id'])
            self.assertEqual(view['rounds'][0]['group'],view['rounds'][1]['group'])
            self.assertNotEqual(view['rounds'][0]['group'],view['rounds'][2]['group'])
            self.assertTrue(view['warnings'])
            self.assertEqual(view['rounds'][1]['parent'],'base')

    def test_invalid_metrics_and_custom_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manager=Projects(root,PYTHONPATH)
            self.addCleanup(manager.close)
            (root/'studio.environment.json').write_text(json.dumps(dict(version=1,id='x',observe='../other.py')))
            with self.assertRaisesRegex(ValueError,'relative'):
                manager.environments.register(dict(root=str(root)))
            with self.assertRaisesRegex(ValueError,'finite'):
                log_round(root/'studio.rsi.jsonl',series='x',id='r1',protocol='seed',metrics={'score':float('nan')})

    def test_robocasa_and_robotwin_camera_contracts(self):
        args = SimpleNamespace(task='',suite='',seed=3)
        pixels = [1,2]
        casa = Mock()
        casa.reset.return_value = {'robot0_agentview_left_image':pixels}
        create = Mock(return_value=casa)
        with patch.dict(sys.modules, {'robocasa.utils.env_utils':SimpleNamespace(create_env=create)}):
            rgb, meta = observe_environment.robocasa(args)
        create.assert_called_once_with(env_name='OpenDrawer',split='target',seed=3,camera_names=['robot0_agentview_left'])
        self.assertEqual(rgb,list(reversed(pixels)))
        self.assertEqual(meta['split'],'target')
        casa.close.assert_called_once_with()
        twin = Mock()
        twin.get_obs.return_value = {'observation':{'head_camera':{'rgb':pixels}}}
        adapter = SimpleNamespace(class_decorator=Mock(return_value=twin),load_task_args=Mock(return_value=({},'aloha-agilex')))
        with patch.dict(sys.modules, {'eval_policy_xpolicylab':adapter}), patch.object(sys,'path',sys.path.copy()):
            rgb,meta = observe_environment.robotwin(Path('/fixture'),args)
        twin.setup_demo.assert_called_once_with(now_ep_num=0,seed=3,is_test=True,render_freq=0,eval_mode=True)
        self.assertEqual(meta['task'],'beat_block_hammer')
        self.assertEqual(rgb,pixels)
        twin.close_env.assert_called_once_with()

    def test_case_evidence_and_optional_legacy_fields(self):
        from roborag.studio.rsi_board import checked_round
        old = dict(id='v1', series='test',protocol='simulation')
        self.assertEqual(checked_round(old)['episodes'], [])
        ep = dict(id='task/seed1',outcome='interrupted',cost={'steps':0},tools={'observe':0})
        self.assertEqual(checked_round(dict(old,episodes=[ep]))['episodes'][0]['outcome'], 'interrupted')
        for cases in ([ep, ep], [dict(ep,evidence='../elsewhere')], [dict(ep,cost={'steps':-1})]):
            with self.assertRaises(ValueError):checked_round(dict(old,episodes=cases))

    def test_bundled_push_t_cases_reference_matching_native_reports(self):
        root = ROOT/'examples/studio-project'
        with tempfile.TemporaryDirectory() as tmp:
            manager=Projects(Path(tmp),PYTHONPATH)
            self.addCleanup(manager.close)
            project=manager.open_workspace(root,'review')
            rows=board(manager,project['id'])['rounds']
            self.assertEqual([row['id'] for row in rows],['baseline','summaries','no_plan','fixed','none'])
            for row in rows:
                self.assertEqual(len(row['episodes']),2)
                for ep in row['episodes']:
                    self.assertTrue(ep['evidence_available'])
                    report=json.loads((root/ep['evidence']).read_text())
                    self.assertEqual(report['layout_sha256'],ep['setup'])
                    self.assertEqual(report['native_result']['details']['0']['success'],ep['outcome']=='success')
                    self.assertEqual(report['steps'],ep['cost']['steps'])
                    self.assertEqual(len(report['tool_sequence']),sum(ep['tools'].values()))

    def test_native_case_verdict_and_cost_scope(self):
        from roborag.studio.rsi_board import native_cases
        run=dict(id='attempt',status='completed',recipe={'metadata':{'task':'push_T','seed':1,'layout':0}})
        self.assertEqual(native_cases(run, {'complete':True,'native':{'score':100}})[0]['outcome'],'unscored')
        cases=native_cases(run,{'wall_seconds':10,'native':{'details':{
            '0':{'layout_id':0,'success':True},'1':{'layout_id':1,'success':False}}}})
        self.assertEqual([c['outcome'] for c in cases],['success','failure'])
        self.assertFalse(any(c['cost'] for c in cases))
        self.assertEqual(native_cases(run,{'scored':True,'success':False,'steps':0})[0]['cost'],{'steps':0})
        self.assertEqual(native_cases(run,{'scored':False,'success':False})[0]['outcome'],'unscored')
