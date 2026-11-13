"""Workspace HTTP contracts, independent of simulator assets and model access."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from roborag.studio.service import Studio, serve


class WorkspaceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        (self.base / 'resources').mkdir()
        (self.base / 'resources/task-bundles.json').write_text('{"tasks":{}}')
        with patch('roborag.studio.codex_agent.login_status', return_value={}):
            self.studio = Studio(root=self.base, state=self.base/'state', workspace=self.base/'workspace')
        self.server = serve(self.studio, 0, 'workspace-test')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.studio.close()
        self.temp.cleanup()

    def post(self, path, body):
        request = Request(f'http://127.0.0.1:{self.server.server_port}/api'+path,
                          json.dumps(body).encode(), {'Authorization':'Bearer workspace-test'})
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def test_default_workspace_is_explicit_idempotent_and_preserves_user_files(self):
        self.assertFalse(self.studio.workspace.exists())
        first = self.post('/workspace/default', {})
        self.assertEqual(first['path'], str(self.studio.workspace))
        self.assertEqual(json.loads((self.studio.workspace/'linkmind.studio.json').read_text())['recipes'], {})
        (self.studio.workspace/'README.md').write_text('User documentation')
        (self.studio.workspace/'linkmind.studio.json').write_text('User unfinished edit')
        self.assertEqual(self.post('/workspace/default', {}), first)
        self.assertEqual((self.studio.workspace/'README.md').read_text(), 'User documentation')
        self.assertEqual((self.studio.workspace/'linkmind.studio.json').read_text(), 'User unfinished edit')

    def test_save_checks_owner_and_revision_and_start_rejects_unreviewed_changes(self):
        root = self.post('/workspace/default', {})['path']
        opened = self.post('/workspace/open', {'path':root, 'session_id':'chat-a'})
        endpoint = '/projects/'+opened['id']
        content = json.dumps({'version':1, 'recipes':{'test':{'argv':[sys.executable, '-c', 'print(1)']}}})
        body = {'session_id':'chat-b', 'content':content, 'revision':opened['configuration']['revision']}
        with self.assertRaises(HTTPError) as error:
            self.post(endpoint+'/configuration', body)
        self.assertEqual(error.exception.code, 400)
        body['session_id'] = 'chat-a'
        saved = self.post(endpoint+'/configuration', body)
        self.assertNotEqual(saved['revision'], body['revision'])
        with self.assertRaises(HTTPError) as error:
            self.post(endpoint+'/start', {'recipe':'test','request_id':'one','config_revision':body['revision']})
        self.assertIn('refresh and review', error.exception.read().decode())
        self.assertEqual(self.studio.projects.list_runs(), [])
        with self.assertRaises(HTTPError):
            self.post(endpoint+'/configuration', body)
        self.assertEqual((Path(root)/'linkmind.studio.json').read_text(), content)


if __name__ == '__main__':
    unittest.main()
