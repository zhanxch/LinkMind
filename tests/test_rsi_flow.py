import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from roborag.studio.rsi_flow import TRACE, emit, snapshot


class FlowSnapshotTest(unittest.TestCase):
    def test_partial_records_and_actual_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(project=lambda _: {'path':tmp})
            (root/'change.patch').touch()
            emit(root/TRACE,run='coding',round=1,stage='review',candidate='A',status='passed',
                 links=[{'label':'diff','path':'change.patch'},{'label':'outside','path':'../outside'}])
            emit(root/TRACE,run='coding',round=1,stage='decision',candidate='A',status='done')
            with (root/TRACE).open('a') as f:
                f.write('{"run":"incomplete"')
            round_ = snapshot(p,'project')['rounds'][0]
            a = round_['candidates']['A']
            self.assertNotIn('activation',a)
            self.assertEqual(a['review']['links'],[{'label':'diff','path':'change.patch'}])
            self.assertNotIn('evaluation',a)
            self.assertEqual(snapshot(p,'project')['warnings'],[])

    def test_opens_actual_stage_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(project=lambda _: {'path':tmp})
            (root/'outputs').mkdir()
            (root/'studio.rsi.sources.json').write_text(json.dumps({'version':1,'sources':[{'kind':'openrsi','path':'outputs'}]}))
            def save(name,value):
                (root/'outputs'/name).write_text(json.dumps(value)+'\n')
            save('scheduler-state.json',{'status':'error','error':'three unscored'})
            save('learning-state.json',{'status':'waiting_for_training'})
            save('protocol.json',{'inputs':[{'split':'train'}]})
            save('ledger.jsonl',{'split':'train','native_success':None})
            record=snapshot(p,'project')['rounds'][0]
            self.assertEqual(record['meta']['status'],'blocked')
            self.assertEqual(record['shared']['evidence']['progress'],{'done':1,'total':2})
            self.assertFalse(record['candidates'])
            self.assertNotIn('activation',record['shared'])

    def test_demo_runs_actual_tests_and_rejects_before_scoring(self):
        import subprocess
        import sys
        demo=Path(__file__).resolve().parents[1]/'examples/studio-project/rsi_workflow_demo.py'
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable,str(demo),'--interval','0'],cwd=tmp,check=True)
            p=SimpleNamespace(project=lambda _: {'path':tmp})
            round_=snapshot(p,'project')['rounds'][0]
            lanes=round_['candidates']
            self.assertEqual(lanes['A']['evaluation']['metrics']['通过'],8)
            self.assertEqual(lanes['A']['activation']['status'],'adopted')
            self.assertTrue(lanes['A']['activation']['links'])
            self.assertEqual(lanes['B']['review']['status'],'rejected')
            self.assertNotIn('evaluation',lanes['B'])
            self.assertLess(lanes['C']['evaluation']['metrics']['通过'],8)
            self.assertEqual(lanes['C']['decision']['status'],'rejected')
