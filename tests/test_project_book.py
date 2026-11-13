"""Project continuity and acceptance contracts; no simulator or model calls."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import sys
import time
from urllib.error import HTTPError
import unittest

from roborag.studio.project_book import ProjectBook
import test_studio_workspace as http_fixture


class BookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.book = ProjectBook(self.root/'state')
        self.project = self.book.open(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def change(self, operation, data, actor='user'):
        result = self.book.change(self.project['id'], self.project['revision'], operation, data, actor)
        self.project = result
        return result

    def goal(self, kind='reproduce', parent=''):
        self.change('create_objective', dict(kind=kind, title=kind, intent='Deliver a verified report', criteria=['Report supports the claim'], parent_id=parent))
        return self.project['objectives'][-1]['id']

    def test_identity_restart_and_separate_directories(self):
        goal = self.goal()
        other = self.root/'other'; other.mkdir()
        self.assertNotEqual(self.book.open(other)['id'], self.project['id'])
        restarted = ProjectBook(self.root/'state')
        self.assertEqual(restarted.open(self.root)['objectives'][0]['id'], goal)
        link = self.root/'alias'; link.symlink_to(self.root)
        self.assertEqual(restarted.open(link)['id'], self.project['id'])

    def test_concurrent_writes_preserve_old_revision_and_reject_lost_update(self):
        self.goal()
        revision = self.project['revision']
        def write(number):
            try:
                self.book.change(self.project['id'], revision, 'save_record', dict(kind='finding', text=str(number)), 'agent')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(write, [1, 2])), [False, True])
        self.assertEqual(self.book.get(self.project['id'], revision)['records'], [])
        self.assertEqual(len(self.book.get(self.project['id'])['records']), 1)
        self.assertEqual(len(self.book.history(self.project['id'])), 3)

    def test_types_derivation_and_dependencies(self):
        first = self.goal('reproduce')
        self.goal('optimize', first); self.goal('develop')
        self.assertEqual(self.project['objectives'][1]['parent_id'], first)
        self.assertEqual(len(self.project['work']), 12)
        a,b = self.project['work'][:2]
        self.change('save_work',dict(id=b['id'],changes={'depends_on':[a['id']]}))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.change('save_work',dict(id=a['id'],changes={'depends_on':[b['id']]}))
        with self.assertRaisesRegex(ValueError, 'Complete dependencies'):
            self.change('save_work',dict(id=b['id'],changes={'state':'active'}))
        with self.assertRaisesRegex(ValueError, 'other work'):
            self.change('save_work',dict(id=b['id'],changes={'depends_on':[self.project['work'][-1]['id']]}))

    def test_acceptance_requires_user_evidence_and_finished_work(self):
        goal = self.goal()
        criterion = self.project['objectives'][0]['criteria'][0]['id']
        with self.assertRaisesRegex(ValueError, 'Only the user'):
            self.change('close_objective',dict(id=goal,outcome='achieved',conclusion='done'),'agent')
        with self.assertRaisesRegex(ValueError, 'user action'):
            self.change('review_criterion',dict(objective_id=goal,id=criterion,verdict='met',evidence_ids=[]),'agent')
        with self.assertRaisesRegex(ValueError, 'Attach evidence'):
            self.change('review_criterion',dict(objective_id=goal,id=criterion,verdict='met',evidence_ids=[]))
        self.change('save_record',dict(kind='evidence',text='Verified original report',reference='report.json'))
        evidence = self.project['records'][-1]['id']
        self.change('review_criterion',dict(objective_id=goal,id=criterion,verdict='met',evidence_ids=[evidence]))
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.change('save_record',dict(id=evidence,kind='evidence',text='Altered',reference='other.json'))
        with self.assertRaisesRegex(ValueError, 'Finish or explicitly cancel'):
            self.change('close_objective',dict(id=goal,outcome='achieved',conclusion='done'))
        for work in self.project['work'][:]:
            self.change('save_work',dict(id=work['id'],changes={'state':'done','verification':'Reviewed output'}))
        self.change('close_objective',dict(id=goal,outcome='achieved',conclusion='Accepted against report'))
        self.assertEqual(self.project['objectives'][0]['state'],'closed')
        with self.assertRaisesRegex(ValueError, 'Closed objectives'):
            self.change('update_objective',dict(id=goal,changes={'state':'active'}),'agent')
        self.change('update_objective',dict(id=goal,changes={'state':'review'}))
        self.change('update_objective',dict(id=goal,changes={'intent':'Different delivery'}))
        self.assertEqual(self.project['objectives'][0]['criteria'][0]['verdict'],'pending')
        with self.assertRaisesRegex(ValueError,'Only the user'):
            self.change('update_objective',dict(id=goal,changes={'criteria':['Easier']}),'agent')
        self.change('update_objective',dict(id=goal,changes={'state':'paused'}))
        with self.assertRaisesRegex(ValueError,'resume'):
            self.change('update_objective',dict(id=goal,changes={'state':'ready'}),'agent')


class ProjectHTTPTests(unittest.TestCase):
    setUp = http_fixture.WorkspaceHTTPTests.setUp
    tearDown = http_fixture.WorkspaceHTTPTests.tearDown
    post = http_fixture.WorkspaceHTTPTests.post

    def test_same_workspace_joins_context_and_historical_runs(self):
        root = self.post('/workspace/default', {})['path']
        first = self.post('/workspace/open', {'path':root,'session_id':'first'})
        context = self.studio.project_context(first['id'])
        result = self.post('/projects/'+first['id']+'/change', dict(session_id='first',revision=0,operation='create_objective',data=dict(kind='develop',title='Delivery',intent='Working feature',criteria=['Integration verified'])))
        second = self.post('/workspace/open', {'path':root,'session_id':'second'})
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(self.studio.project_context(second['id'])['project'],result['project'])
        self.assertEqual(context['project']['id'],result['project']['id'])
        goal = result['project']['objectives'][0]['id']
        with self.assertRaisesRegex(ValueError,'changed'):
            self.studio.project_run_context(second['id'], dict(objective_id=goal,project_revision=0))
        self.studio.project_change(first['id'],dict(revision=1,operation='update_objective',data=dict(id=goal,changes={'state':'paused'})),'user')
        with self.assertRaisesRegex(ValueError,'paused'):
            self.studio.project_run_context(second['id'],dict(objective_id=goal,project_revision=2))

    def test_evidence_is_project_scoped_and_fingerprinted(self):
        root = Path(self.post('/workspace/default', {})['path'])
        opened = self.post('/workspace/open', {'path':str(root),'session_id':'first'})
        (root/'report.json').write_text('{"status":"synthetic validation"}')
        def record(reference,revision=0):
            return self.studio.project_change(opened['id'],dict(revision=revision,operation='save_record',data=dict(kind='evidence',text='report',reference=reference,_source={'forged':True})),'agent')
        value = record('report.json')
        source = value['project']['records'][0]['source']
        self.assertEqual(len(source['sha256']),64)
        self.assertNotIn('forged',source)
        (root/'escape').symlink_to(self.base/'resources/task-bundles.json')
        for reference in ('../resources/task-bundles.json','escape','run:nonexistent'):
            with self.assertRaises((ValueError, FileNotFoundError)):
                record(reference,1)
        self.assertEqual(self.studio.project_context(opened['id'])['project']['revision'],1)

    def test_run_receipt_retains_goal_and_later_conversation_can_follow(self):
        root = Path(self.post('/workspace/default', {})['path'])
        (root/'linkmind.studio.json').write_text(json.dumps({'version':1,'recipes':{'demo':{'argv':[sys.executable,'-c','print("test output")']}}}))
        first = self.post('/workspace/open', {'path':str(root),'session_id':'first'})
        context = self.studio.project_change(first['id'],dict(revision=0,operation='create_objective',data=dict(kind='reproduce',title='Test',intent='Validate demo',criteria=['Review output'])),'user')
        goal = context['project']['objectives'][0]['id']
        body = dict(recipe='demo',request_id='once',objective_id=goal,project_revision=1)
        run = self.post('/projects/'+first['id']+'/start',body)
        deadline = time.monotonic()+10
        while time.monotonic()<deadline and self.studio.projects.live(run['id'])['status']=='running':
            time.sleep(.05)
        self.assertEqual(self.studio.projects.live(run['id'])['status'],'completed')
        self.assertEqual(self.studio.project_context(first['id'])['project']['objectives'][0]['state'],'ready')
        self.assertEqual(self.post('/projects/'+first['id']+'/start',body)['id'],run['id'])
        with self.assertRaises(HTTPError):
            self.post('/projects/'+first['id']+'/start',{**body,'objective_id':''})
        with self.assertRaises(ValueError):
            self.studio.projects.check('second',run_id=run['id'])
        second = self.post('/workspace/open',{'path':str(root),'session_id':'second'})
        self.studio.projects.check('second',run_id=run['id'])
        with self.assertRaises(ValueError):
            self.studio.projects.check('second',project_id=first['id'])
        self.assertEqual(self.studio.project_context(second['id'])['runs'][0]['id'],run['id'])
        outside = self.base/'different';outside.mkdir()
        other = self.post('/workspace/open',{'path':str(outside),'session_id':'other'})
        with self.assertRaisesRegex(ValueError,'another project'):
            self.studio.project_change(other['id'],dict(revision=0,operation='save_record',data=dict(kind='evidence',text='wrong',reference='run:'+run['id'])),'agent')
