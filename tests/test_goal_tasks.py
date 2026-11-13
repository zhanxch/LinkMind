"""Goal task persistence, ownership transfer and evidence attribution."""
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
import test_studio_workspace as fixtures

class GoalTaskTests(unittest.TestCase):
    setUp = fixtures.WorkspaceHTTPTests.setUp
    tearDown = fixtures.WorkspaceHTTPTests.tearDown
    post = fixtures.WorkspaceHTTPTests.post

    def open(self, session='first'):
        root = self.post('/workspace/default', {})['path']
        registration = self.post('/workspace/open', {'path':root, 'session_id':session})
        return registration

    def change(self, reg, operation, data):
        context = self.studio.project_context(reg['id'])
        return self.studio.goal_task(reg['id'], dict(session_id=reg['session_id'],
            revision=context['project']['revision'], operation=operation, data=data))

    def create(self, reg, kind='reproduce'):
        context = self.change(reg,'create_goal_task',dict(kind=kind,request='Preserve the original model and reproduce Push-T'))
        return context['project']['objectives'][-1]['id']

    def attach(self, reg, task, native='goal-1'):
        return self.change(reg,'attach_goal_task',dict(id=task,native_goal_id=native))

    def sync(self, reg, task, phase, revision, native='goal-1'):
        return self.change(reg,'sync_goal_task',dict(id=task,native_goal_id=native,native_revision=revision,phase=phase))

    def test_three_types_start_from_instruction_without_invented_work(self):
        first = self.open()
        for kind in ('reproduce','optimize','develop'):
            task = self.create(first,kind)
        context = self.studio.project_context(first['id'])
        self.assertEqual([g['kind'] for g in context['project']['objectives']], ['reproduce','optimize','develop'])
        self.assertEqual(context['project']['work'], [])
        self.assertEqual(context['project']['objectives'][-1]['criteria'], [])
        second = self.open('second')
        self.assertEqual(self.studio.project_context(second['id'])['project'], context['project'])
        # Re-open the database, as on a host restart.
        from roborag.studio.project_book import ProjectBook
        self.assertEqual(ProjectBook(self.studio.book.path.parent).get(context['project']['id']),context['project'])

    def test_transfer_prevents_stale_native_events_and_cross_conversation_writes(self):
        first = self.open(); task = self.create(first)
        self.attach(first,task); self.sync(first,task,'active',1)
        second = self.open('second'); self.attach(second,task,'goal-2')
        value = self.sync(second,task,'active',1,'goal-2')
        record = value['project']['objectives'][0]
        self.assertEqual(record['sessions'],['first','second'])
        self.assertEqual(record['bindings'],{'first':'goal-1','second':'goal-2'})
        with self.assertRaisesRegex(ValueError,'moved'):
            self.sync(first,task,'complete',20)
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.sync(second,task,'paused',1,'goal-2')
        with self.assertRaisesRegex(ValueError,'another conversation'):
            self.studio.project_change(first['id'],dict(revision=value['project']['revision'],operation='refine_task',data=dict(id=task,changes={'intent':'wrong owner'})),'agent')
        value = self.studio.project_change(second['id'],dict(revision=value['project']['revision'],operation='refine_task',data=dict(id=task,changes={'intent':'Review original protocol','criteria':['Keep original budget'],'next_action':'Check dependencies'})),'agent')
        self.assertEqual(value['project']['objectives'][0]['original_request'],'Preserve the original model and reproduce Push-T')
        self.sync(second,task,'paused',2,'goal-2')
        self.sync(second,task,'active',3,'goal-2')
        value = self.sync(second,task,'complete',4,'goal-2')
        self.assertEqual(value['project']['objectives'][0]['outcome'],'agent_completed')
        with self.assertRaisesRegex(ValueError,'complete'):
            self.attach(first,task,'goal-3')

    def test_takeover_cannot_steal_a_task_changed_since_selection(self):
        first = self.open(); task = self.create(first); self.attach(first,task)
        second = self.open('second'); self.attach(second,task,'goal-2')
        with self.assertRaisesRegex(ValueError,'ownership changed'):
            self.change(first,'attach_goal_task',dict(id=task,native_goal_id='goal-3',expected_owner=['first','goal-1']))

    def test_activation_and_edits_preserve_original_instruction(self):
        first = self.open(); task = self.create(first); self.attach(first,task)
        self.change(first,'sync_goal_task',dict(id=task,native_goal_id='goal-1',native_revision=1,phase='active',activation='armed'))
        value = self.change(first,'sync_goal_task',dict(id=task,native_goal_id='goal-1',native_revision=1,phase='active',activation='disarmed'))
        self.assertEqual(value['project']['objectives'][0]['native_activation'],'disarmed')
        value = self.change(first,'sync_goal_task',dict(id=task,native_goal_id='goal-1',native_revision=2,phase='active',activation='disarmed',request='Also retain failed attempts'))
        goal = value['project']['objectives'][0]
        self.assertEqual(goal['request'],'Also retain failed attempts')
        self.assertNotEqual(goal['original_request'],goal['request'])

    def test_user_routes_cannot_forge_native_goal_state(self):
        first = self.open(); task = self.create(first)
        with self.assertRaises(HTTPError):
            self.post('/projects/'+first['id']+'/goal-task',dict(session_id='first',revision=1,operation='attach_goal_task',data=dict(id=task,native_goal_id='fake')))
        with self.assertRaisesRegex(ValueError,'controller'):
            self.studio.project_change(first['id'],dict(revision=1,operation='sync_goal_task',data=dict(id=task)),'agent')
        with self.assertRaises(ValueError):
            self.studio.goal_task(first['id'],dict(session_id='second',revision=1,operation='attach_goal_task',data=dict(id=task,native_goal_id='fake')))

    def test_managed_run_associates_task_without_manual_ids(self):
        reg = self.open(); task = self.create(reg); self.attach(reg,task); self.sync(reg,task,'active',1)
        value = self.studio.project_run_context(reg['id'], {})
        self.assertEqual(value['objective_id'], task)
        self.sync(reg,task,'paused',2)
        self.assertNotIn('objective_id',self.studio.project_run_context(reg['id'], {}))
        self.sync(reg,task,'cleared',3)
        value = self.studio.project_context(reg['id'])['project']['objectives'][0]
        self.assertEqual(value['state'],'paused')
        self.assertEqual(value['owner_session_id'],'')
        self.assertEqual(value['original_request'],'Preserve the original model and reproduce Push-T')

if __name__ == '__main__': unittest.main()
