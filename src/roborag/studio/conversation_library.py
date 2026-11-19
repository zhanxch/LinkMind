"""Conversation folders within native DSH workspaces; no agent lineage or cwd mutation."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid


class ConversationLibrary:
    def __init__(self, state):
        self.path = Path(state) / 'conversation-library.sqlite3'
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS library (id INTEGER PRIMARY KEY, document TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO library VALUES (1, ?)',
                       (json.dumps(dict(revision=0, folders=[], members={})),))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def snapshot(self):
        with self.connection() as db:
            return json.loads(db.execute('SELECT document FROM library WHERE id=1').fetchone()[0])

    def change(self, request):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            doc = json.loads(db.execute('SELECT document FROM library WHERE id=1').fetchone()[0])
            if request.get('revision') != doc['revision']:
                raise ValueError('会话目录已在其他窗口更新，请刷新后重试')
            op, data = request.get('operation'), request.get('data', {})
            if not isinstance(data, dict):
                raise ValueError('目录操作格式有误')
            folders = {f['id']: f for f in doc['folders']}

            def folder(key):
                if not isinstance(key, str) or key not in folders:
                    raise ValueError('文件夹不存在，请刷新')
                return folders[key]

            def parent(key):
                if key is not None:
                    folder(key)
                return key

            def name(value):
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80 or any(c in value for c in '/\\\n\r\0'):
                    raise ValueError('名称需为 1–80 个字符，不能包含路径分隔符')
                return value.strip()

            def workspace(value):
                if not isinstance(value, str) or not value or len(value) > 300:
                    raise ValueError('请先选择项目工作区')
                return value

            if op == 'migrate_workspaces':
                # Only migrate old, unscoped classifications. The native catalog supplies
                # workspace membership. Unknown sessions keep their original folders.
                memberships = data.get('session_workspaces', {})
                if not isinstance(memberships, dict) or len(memberships) > 100000:
                    raise ValueError('工作区成员格式有误')
                for key, value in memberships.items():
                    if not isinstance(key, str):
                        raise ValueError('会话标识有误')
                    workspace(value)
                default = data.get('default_workspace_id')
                if default is not None:
                    workspace(default)
                changed = False
                roots = [f for f in folders.values() if f['parent_id'] is None and not f.get('workspace_id')]
                for root in roots:
                    subtree = [root]
                    for node in subtree:
                        subtree.extend(f for f in folders.values() if f['parent_id'] == node['id'])
                    ids = {f['id'] for f in subtree}
                    members = {sid: fid for sid, fid in doc['members'].items() if fid in ids}
                    scopes = {memberships.get(sid) for sid in members} if members else {default}
                    known = sorted(scope for scope in scopes if scope is not None)
                    if not known:
                        continue
                    for index, scope in enumerate(known):
                        reuse = None not in scopes and index == len(known)-1
                        remap = {f['id']: f['id'] if reuse else uuid.uuid4().hex[:16] for f in subtree}
                        for original in subtree:
                            copied = dict(original, id=remap[original['id']],
                                          parent_id=remap.get(original['parent_id']), workspace_id=scope)
                            if copied['parent_id'] is None:
                                base, suffix = copied['name'], 2
                                existing = {f['name'].casefold() for f in folders.values()
                                            if f.get('workspace_id') == scope and f['parent_id'] is None}
                                while copied['name'].casefold() in existing:
                                    copied['name'] = f'{base[:70]} ({suffix})'; suffix += 1
                            folders[copied['id']] = copied
                        for sid, fid in members.items():
                            if memberships.get(sid) == scope:
                                doc['members'][sid] = remap[fid]
                        changed = True
                if not changed:
                    return doc
            elif op == 'create_folder':
                if len(folders) >= 1000:
                    raise ValueError('文件夹数量已达上限')
                scope = workspace(data.get('workspace_id'))
                target = parent(data.get('parent_id'))
                if target is not None and folder(target).get('workspace_id') != scope:
                    raise ValueError('文件夹必须位于所属项目工作区内')
                item = dict(id=uuid.uuid4().hex[:16], name=name(data.get('name')), parent_id=target, workspace_id=scope)
                folders[item['id']] = item
            elif op == 'rename_folder':
                folder(data.get('id'))['name'] = name(data.get('name'))
            elif op == 'move_folder':
                item = folder(data.get('id'))
                scope, target = workspace(data.get('workspace_id')), parent(data.get('parent_id'))
                if item.get('workspace_id') != scope or (target is not None and folder(target).get('workspace_id') != scope):
                    raise ValueError('只能在同一项目工作区内整理文件夹')
                item['parent_id'] = target
            elif op == 'remove_folder':
                key = folder(data.get('id'))['id']
                if any(f['parent_id'] == key for f in folders.values()) or key in doc['members'].values():
                    raise ValueError('请先移出会话和子文件夹；只允许移除空文件夹')
                del folders[key]
            elif op == 'move_session':
                key = data.get('session_id')
                if not isinstance(key, str) or not key or len(key) > 200:
                    raise ValueError('会话标识有误')
                target = parent(data.get('folder_id'))
                scope = workspace(data.get('workspace_id'))
                if target is not None and folder(target).get('workspace_id') != scope:
                    raise ValueError('只能在会话所属项目工作区内归类；不会更改执行目录')
                # Root membership keeps intentionally created blank chats visible.
                doc['members'][key] = target
            else:
                raise ValueError('未知目录操作')

            if len(folders) > 1000:
                raise ValueError('文件夹数量已达上限')
            names = set()
            for item in folders.values():
                pair = (item.get('workspace_id'), item['parent_id'], item['name'].casefold())
                if pair in names:
                    raise ValueError('同一层级已有这个名称的文件夹')
                names.add(pair)
                seen, current = set(), item
                while current:
                    if current['id'] in seen:
                        raise ValueError('文件夹不能移入自己或自己的子文件夹')
                    seen.add(current['id'])
                    if len(seen) > 32:
                        raise ValueError('目录层级最多为 32 层')
                    current = folders.get(current['parent_id'])
            doc['folders'] = list(folders.values())
            doc['revision'] += 1
            db.execute('UPDATE library SET document=? WHERE id=1', (json.dumps(doc, ensure_ascii=False),))
            return doc
