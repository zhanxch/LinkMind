import json
from pathlib import Path
import tempfile
import unittest
from roborag.studio.control_conversation import read_conversation, validate_source, MAX_LINE
from roborag.studio.conversation_library import ConversationLibrary

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.file=self.root/'agent-events.jsonl'
    def tearDown(self):self.tmp.cleanup()
    def emit(self,event):
        with self.file.open('ab') as f:f.write(json.dumps(event,ensure_ascii=False).encode()+b'\n')
    def test_persistent_messages_tools_and_partial_utf8(self):
        self.emit({'type':'thread.started','thread_id':'actual-thread'})
        self.emit({'type':'item.started','item':{'id':'tool-1','type':'command_execution','command':'robo observe','status':'in_progress'}})
        page=read_conversation(self.root)
        self.assertEqual(page['events'][0]['thread_id'],'actual-thread')
        self.assertEqual(page['events'][1]['item']['arguments'],'robo observe')
        raw=json.dumps({'type':'item.completed','item':{'id':'tool-1','type':'command_execution','command':'robo observe','aggregated_output':'真实工具结果','exit_code':0}},ensure_ascii=False).encode()+b'\n'
        with self.file.open('ab') as f:f.write(raw[:-5])
        partial=read_conversation(self.root,offset=page['next_offset'],source=page['source'])
        self.assertEqual(partial['next_offset'],page['next_offset']);self.assertFalse(partial['events'])
        with self.file.open('ab') as f:f.write(raw[-5:])
        complete=read_conversation(self.root,offset=partial['next_offset'],source=page['source'])
        self.assertFalse(complete['reset']);self.assertEqual(complete['events'][0]['item']['id'],'tool-1')
        self.assertEqual(complete['events'][0]['item']['output'],'真实工具结果')
        self.assertEqual(complete['events'][0]['item']['status'],'completed')
    def test_missing_corrupt_rotation_and_truncation(self):
        self.assertFalse(read_conversation(self.root)['available'])
        self.file.write_text('not json\n')
        self.emit({'type':'item.completed','item':{'id':'msg','type':'agent_message','text':'verbatim'}})
        page=read_conversation(self.root);self.assertEqual(len(page['warnings']),1)
        self.assertEqual(page['events'][0]['item']['text'],'verbatim')
        self.file.rename(self.root/'old.jsonl');self.emit({'type':'thread.started','thread_id':'new'})
        new=read_conversation(self.root,offset=page['next_offset'],source=page['source']);self.assertTrue(new['reset'])
        self.file.write_text('')
        self.assertTrue(read_conversation(self.root,offset=new['next_offset'],source=new['source'])['reset'])
    def test_api_adapter_and_paths(self):
        for value in [{'format':'logs','path':'agent-events.jsonl'},{'format':'codex-jsonl','path':'../secret'},{'format':'codex-jsonl','path':'/tmp/private'}]:
            with self.assertRaises(ValueError):validate_source(value)
        self.file.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):read_conversation(self.root)
        self.file.unlink()
        self.emit({'type':'tool','id':'api-1','name':'move_arm','arguments':{'x':1},'output':{'ok':True},'status':'completed'})
        page=read_conversation(self.root,{'format':'linkmind-events','path':'agent-events.jsonl'})
        self.assertEqual(page['events'][0]['item']['output'],{'ok':True})
    def test_openrsi_convention_and_oversized_record(self):
        folder=self.root/'hexashell';folder.mkdir();self.file=folder/'agent-events.jsonl'
        self.emit({'type':'thread.started','thread_id':'nested'})
        page=read_conversation(self.root);self.assertEqual(page['path'],'hexashell/agent-events.jsonl')
        with self.file.open('ab') as f:f.write(b'x'*(MAX_LINE+2)+b'\n')
        next_page=read_conversation(self.root,offset=page['next_offset'],source=page['source'])
        self.assertEqual(next_page['next_offset'],page['next_offset']);self.assertTrue(next_page['warnings']);self.assertFalse(next_page['more'])

class LibraryTests(unittest.TestCase):
    def test_persistence_independent_chats_cycles_and_concurrent_revision(self):
        with tempfile.TemporaryDirectory() as root:
            lib=ConversationLibrary(root)
            def change(op,**data):return lib.change({'revision':lib.snapshot()['revision'],'operation':op,'data':{'workspace_id':'project-a',**data}})
            a=change('create_folder',name='复现')['folders'][0]['id']
            b=change('create_folder',name='HexaShell',parent_id=a)['folders'][1]['id']
            change('move_session',session_id='independent-chat',folder_id=b)
            saved=lib.snapshot()
            self.assertEqual(ConversationLibrary(root).snapshot(),saved)
            for op,data in [('move_folder',dict(id=a,parent_id=b)),('remove_folder',dict(id=b)),('create_folder',dict(name='复现'))]:
                with self.assertRaises(ValueError):change(op,**data)
                self.assertEqual(lib.snapshot(),saved)
            change('rename_folder',id=a,name='任务复现')
            with self.assertRaises(ValueError):lib.change({'revision':saved['revision'],'operation':'remove_folder','data':{'id':b}})
            change('move_session',session_id='independent-chat',folder_id=None)
            change('remove_folder',id=b)
            self.assertEqual(lib.snapshot()['members'],{'independent-chat':None})

    def test_workspace_scope_cannot_be_changed_by_classification(self):
        with tempfile.TemporaryDirectory() as root:
            lib=ConversationLibrary(root)
            def change(op,**data):return lib.change({'revision':lib.snapshot()['revision'],'operation':op,'data':data})
            a=change('create_folder',name='修复',workspace_id='a')['folders'][0]['id']
            b=change('create_folder',name='修复',workspace_id='b')['folders'][1]['id']
            change('move_session',session_id='a-chat',workspace_id='a',folder_id=a)
            before=lib.snapshot()
            for op,data in [
                ('create_folder',dict(name='child',parent_id=a,workspace_id='b')),
                ('move_folder',dict(id=a,parent_id=b,workspace_id='a')),
                ('move_folder',dict(id=a,parent_id=None,workspace_id='b')),
                ('move_session',dict(session_id='a-chat',folder_id=b,workspace_id='a')),
            ]:
                with self.assertRaises(ValueError):change(op,**data)
                self.assertEqual(before,lib.snapshot())
            change('move_session',session_id='a-chat',folder_id=None,workspace_id='a')
            self.assertIsNone(lib.snapshot()['members']['a-chat'])

    def test_legacy_mixed_workspace_folders_keep_every_session(self):
        with tempfile.TemporaryDirectory() as root:
            lib=ConversationLibrary(root)
            old=dict(revision=1,folders=[dict(id='f',name='复现',parent_id=None),dict(id='g',name='HexaShell',parent_id='f')],members={'a1':'g','b1':'g','unknown':'f'})
            with lib.connection() as db:db.execute('UPDATE library SET document=? WHERE id=1',(json.dumps(old),))
            result=lib.change(dict(revision=1,operation='migrate_workspaces',data=dict(session_workspaces={'a1':'a','b1':'b'},default_workspace_id='a')))
            folders={f['id']:f for f in result['folders']}
            for sid,scope in [('a1','a'),('b1','b')]:
                child=folders[result['members'][sid]]
                self.assertEqual(child['name'],'HexaShell');self.assertEqual(child['workspace_id'],scope)
                self.assertEqual(folders[child['parent_id']]['name'],'复现')
            self.assertEqual(result['members']['unknown'],'f')
            self.assertEqual(old['folders'],[folders['f'],folders['g']])
            result2=lib.change(dict(revision=result['revision'],operation='migrate_workspaces',data=dict(session_workspaces={'unknown':'c'})))
            self.assertEqual(result2['members']['unknown'],'f')
            self.assertEqual(next(f for f in result2['folders'] if f['id']=='f')['workspace_id'],'c')

if __name__=='__main__':unittest.main()
