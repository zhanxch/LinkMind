"""Portable entry point and publication integrity checks."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_public_results, prepare_task, run_task


class PublicReleaseTests(unittest.TestCase):
    def test_launcher_uses_task_bank_and_preserves_user_override(self):
        for task in ('stack_blocks', 'fold_clothes', 'push_T'):
            for override in (False, True):
                args = ['run_task.py', '--task', task, '--help']
                if override:
                    args += ['--bank', '/custom/bank']
                with patch.object(sys, 'argv', args), patch('roborag.rag_runner.main') as launch:
                    run_task.main()
                    launch.assert_called_once()
                    self.assertEqual(sys.argv.count('--bank'), 1)
                    bank = sys.argv[sys.argv.index('--bank') + 1]
                    self.assertEqual(bank, '/custom/bank' if override else str(run_task.ROOT /
                        json.loads((run_task.ROOT / 'resources/task-bundles.json').read_text())['tasks'][task]['install']))

    def test_native_report_tampering_and_missing_score_are_rejected(self):
        row = json.loads((build_public_results.ROOT / 'results/local-attempts.json').read_text())[0]
        source = dict(row, native_result=row['original_native_path'])
        checked = build_public_results.verify_native(source, 'fold_clothes', 'first', 0, False)
        self.assertTrue(checked['success'])
        altered = dict(source, native_sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'changed'):
            build_public_results.verify_native(altered, 'fold_clothes', 'first', 0, False)
        with self.assertRaisesRegex(ValueError, 'no native evidence'):
            build_public_results.verify_native(dict(source, native_result=None), 'fold_clothes', 'first', 0, False)

    def test_installer_refuses_overwrite_and_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'resources/bank').mkdir(parents=True)
            (root / 'resources/bank/a.json').write_text('{}')
            manifest = dict(tasks=dict(example=dict(bundle='resources/bank', install='artifacts/bank', train=[],
                metadata_sha256={'a.json': hashlib.sha256(b'{}').hexdigest()})))
            (root / 'resources/task-bundles.json').write_text(json.dumps(manifest))
            prepare_task.prepare('example', root=root)
            (root / 'artifacts/bank/a.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'Refusing to replace'):
                prepare_task.prepare('example', root=root)
            self.assertEqual((root / 'artifacts/bank/a.json').read_text(), '{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'escapes'):
                prepare_task.child(root, '../outside')


if __name__ == '__main__':
    unittest.main()
