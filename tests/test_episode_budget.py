"""Budget overrides must reach the simulator without changing native defaults."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from roborag import episode_batch, rag_runner
from roborag.episode_budget import add_budget_argument, apply_control_budget, budget_arguments


class EpisodeBudgetTests(unittest.TestCase):
    def test_native_default_and_explicit_override_only_change_limit(self):
        parser = argparse.ArgumentParser()
        add_budget_argument(parser)
        for requested, expected in [(None, 1300), (2000, 2000)]:
            with self.subTest(requested=requested):
                args = parser.parse_args(budget_arguments(requested))
                marker = object()
                env = SimpleNamespace(step_lim=1300, reward_manager=marker, take_action_cnt=[0])
                info = apply_control_budget(env, args.control_step_limit)
                self.assertEqual(env.step_lim, expected)
                self.assertEqual(info['native_step_limit'], 1300)
                self.assertEqual(info['step_limit'], expected)
                self.assertEqual(info['control_step_limit_override'], requested)
                self.assertEqual(info['budget_mode'], 'native' if requested is None else 'modified')
                self.assertIs(env.reward_manager, marker)
                self.assertEqual(env.take_action_cnt, [0])
        for invalid in [0, -1, True, 1.5, 'native', '2000.5']:
            with self.subTest(invalid=invalid), self.assertRaises(argparse.ArgumentTypeError):
                apply_control_budget(SimpleNamespace(step_lim=1300), invalid)

    def test_batch_forwards_and_records_requested_limit(self):
        original_sleep = time.sleep
        for requested in (None, 2000):
            with self.subTest(requested=requested), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root/'scripts').mkdir()
                (root/'local.runtime.json').write_text(json.dumps(dict(policy_python=sys.executable)))
                (root/'scripts/run_rag_mcp.py').write_text('''import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--control-step-limit',type=int)
a,_=p.parse_known_args();a.output.mkdir()
(a.output/'ready.json').write_text('{}')
(a.output/'result.json').write_text(json.dumps(dict(received_limit=a.control_step_limit)))
''')
                out = root/'batch'
                argv = ['batch', '--task', 'pack_objects_into_box', '--layouts', '1', '--parallel', '1', '--output', str(out)] + budget_arguments(requested)
                with patch.object(episode_batch, 'ROOT', root), patch.object(sys, 'argv', argv), \
                     patch.object(episode_batch, 'resource_sample', return_value=dict(gpu='24000, 0, 0')), \
                     patch.object(episode_batch, 'protocol_sources', return_value={}), \
                     patch.object(episode_batch.time, 'sleep', side_effect=lambda _: original_sleep(.02)), \
                     contextlib.redirect_stdout(io.StringIO()):
                    episode_batch.main()
                status = json.loads((out/'status.json').read_text())
                self.assertTrue(status['complete'])
                self.assertEqual(status['finished'][0]['result']['received_limit'], requested)
                self.assertEqual(json.loads((out/'batch.json').read_text())['control_step_limit'], requested)

    def test_runner_forwards_limit_to_simulator_and_records_request(self):
        runtime = dict(policy_python=sys.executable, sim_python=sys.executable,
                       upstream='/unused/upstream', assets='/unused/assets',
                       sim_library='/unused/lib')
        class LaunchCaptured(Exception):
            pass
        for requested in (None, 2000):
            with self.subTest(requested=requested), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root/'local.runtime.json').write_text(json.dumps(runtime))
                workspace = root/'workspace'; workspace.mkdir()
                out = root/'episode'
                argv = ['runner', '--task', 'pack_objects_into_box', '--bank', str(root/'bank'), '--output', str(out)] + budget_arguments(requested)
                with patch.object(rag_runner, 'ROOT', root), patch.object(sys, 'argv', argv), \
                     patch.object(rag_runner, 'prompt_for', return_value='test'), \
                     patch.object(rag_runner, 'digest', return_value='test-sha'), \
                     patch.object(rag_runner, 'evidence_source_paths', return_value=[]), \
                     patch.object(rag_runner.tempfile, 'mkdtemp', return_value=str(workspace)), \
                     patch.object(rag_runner.signal, 'signal'), \
                     patch.object(rag_runner.subprocess, 'check_output', return_value='test-commit'), \
                     patch.object(rag_runner.subprocess, 'Popen', side_effect=LaunchCaptured) as launch, \
                     self.assertRaises(LaunchCaptured):
                    rag_runner.main()
                command = launch.call_args.args[0]
                if requested is None:
                    self.assertNotIn('--control-step-limit', command)
                else:
                    self.assertEqual(command[command.index('--control-step-limit')+1], str(requested))
                self.assertEqual(json.loads((out/'run.json').read_text())['args']['control_step_limit'], requested)


if __name__ == '__main__':
    unittest.main()
