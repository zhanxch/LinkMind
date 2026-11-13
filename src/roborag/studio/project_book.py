"""Durable project goals and evidence; execution and conversation grants stay separate."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


TEMPLATES = {
    'reproduce': {'name': '复现', 'description': '保留原方案与协议，交付可核对的原始结果和差异报告',
                  'steps': ['核对来源与协议', '准备环境并验证入口', '执行约定范围', '核对结果并交付报告']},
    'optimize': {'name': '优化', 'description': '在固定基线和约束下验证改进，保留未奏效的尝试',
                 'steps': ['确定基线与改进标准', '诊断并提出假设', '实现和比较候选', '独立验证并交付结论']},
    'develop': {'name': '开发', 'description': '围绕使用场景完成实现、集成、验证和可用成果交付',
                'steps': ['明确需求与验收场景', '设计和实现', '集成与场景验证', '文档与版本交付']},
}
STATES = {'ready', 'active', 'blocked', 'paused', 'review'}
WORK_STATES = {'planned', 'active', 'blocked', 'done', 'cancelled'}


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex[:16]


def text(value, label, limit=8000, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f'{label} must be text (1–{limit} characters)' if required else f'Invalid {label}')
    return value.strip()


def find(items, item_id, label):
    item = next((x for x in items if x['id'] == item_id), None)
    if item is None:
        raise ValueError(f'{label} does not belong to this project')
    return item


def strings(value, label, maximum=50):
    if not isinstance(value, list) or len(value) > maximum or any(not isinstance(x, str) for x in value):
        raise ValueError(f'Invalid {label}')
    return list(dict.fromkeys(value))


class ProjectBook:
    def __init__(self, state):
        Path(state).mkdir(parents=True, exist_ok=True)
        self.path = Path(state) / 'project-book.sqlite3'
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, revision INTEGER NOT NULL, document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS history (
                    project_id TEXT NOT NULL, revision INTEGER NOT NULL, at TEXT NOT NULL,
                    actor TEXT NOT NULL, operation TEXT NOT NULL, document TEXT NOT NULL,
                    PRIMARY KEY(project_id, revision)
                );
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def open(self, root):
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError('Project directory does not exist')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document FROM projects WHERE path=?', (str(root),)).fetchone()
            if row:
                return json.loads(row['document'])
            value = {'id': uid(), 'path': str(root), 'name': root.name, 'revision': 0,
                     'created_at': now(), 'updated_at': now(), 'objectives': [], 'work': [], 'records': []}
            encoded = json.dumps(value, ensure_ascii=False)
            db.execute('INSERT INTO projects VALUES (?,?,?,?)', (value['id'], str(root), 0, encoded))
            db.execute('INSERT INTO history VALUES (?,?,?,?,?,?)', (value['id'], 0, now(), 'system', 'create_project', encoded))
            return value

    def get(self, project_id, revision=None):
        with self.db() as db:
            row = (db.execute('SELECT document FROM projects WHERE id=?', (project_id,)).fetchone() if revision is None else
                   db.execute('SELECT document FROM history WHERE project_id=? AND revision=?', (project_id, revision)).fetchone())
            if not row:
                raise ValueError('Unknown persistent project')
            return json.loads(row['document'])

    def history(self, project_id):
        with self.db() as db:
            return [dict(row) for row in db.execute(
                'SELECT revision,at,actor,operation FROM history WHERE project_id=? ORDER BY revision DESC LIMIT 100', (project_id,))]

    def change(self, project_id, revision, operation, data, actor):
        if not isinstance(data, dict) or type(revision) is not int:
            raise ValueError('Supply an object and the current project revision')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if not row:
                raise ValueError('Unknown persistent project')
            if row['revision'] != revision:
                raise ValueError('项目已被其他会话更新，请刷新后核对再保存；草稿已保留')
            value = json.loads(row['document'])
            self.apply(value, operation, data, actor)
            value.update(revision=revision+1, updated_at=now())
            encoded = json.dumps(value, ensure_ascii=False)
            db.execute('UPDATE projects SET revision=?,document=? WHERE id=?', (revision+1, encoded, project_id))
            db.execute('INSERT INTO history VALUES (?,?,?,?,?,?)', (project_id, revision+1, now(), actor, operation, encoded))
            return value

    def apply(self, project, operation, data, actor):
        goals, work, records = (project[k] for k in ('objectives', 'work', 'records'))
        if operation in ('create_goal_task', 'attach_goal_task', 'sync_goal_task'):
            if actor != 'controller':
                raise ValueError('Native Goal bindings are maintained by the DSH controller')
            if operation == 'create_goal_task':
                if data.get('kind') not in TEMPLATES or len(goals) >= 100:
                    raise ValueError('Choose reproduce, optimize or develop (maximum 100 tasks)')
                request = text(data.get('request'), 'task instruction', 8000, True)
                goals.append({'id': uid(), 'mode': 'goal', 'kind': data['kind'], 'title': request[:80],
                    'request': request, 'original_request': request, 'intent': '', 'constraints': '',
                    'criteria': [], 'state': 'ready', 'outcome': None, 'conclusion': '',
                    'created_at': now(), 'next_action': '根据指令和仓库内容完善任务说明',
                    'sessions': [], 'bindings': {}, 'owner_session_id': '', 'native_goal_id': '', 'native_revision': 0})
                return
            goal = find(goals, data.get('id'), 'Task')
            if goal.get('mode') != 'goal':
                raise ValueError('This record is not a native Goal task')
            session = text(data.get('session_id'), 'session', 200, True)
            native_id = text(data.get('native_goal_id'), 'native goal', 200, True)
            if operation == 'attach_goal_task':
                if 'expected_owner' in data and data['expected_owner'] != [goal['owner_session_id'], goal['native_goal_id']]:
                    raise ValueError('Task ownership changed; refresh before continuing')
                if goal['state'] == 'closed':
                    raise ValueError('This task is complete; start a new task for further work')
                if session not in goal['sessions']:
                    goal['sessions'].append(session)
                goal.setdefault('bindings', {})[session] = native_id
                goal.update(owner_session_id=session, native_goal_id=native_id, native_revision=0)
            else:
                if goal['owner_session_id'] != session or goal['native_goal_id'] != native_id:
                    raise ValueError('Task has moved to another conversation')
                revision = data.get('native_revision')
                observation = (revision == goal['native_revision'] and data.get('phase') == goal.get('native_phase')
                               and data.get('activation') in ('armed','disarmed') and data.get('activation') != goal.get('native_activation'))
                if type(revision) is not int or revision < goal['native_revision'] or (revision == goal['native_revision'] and not observation):
                    raise ValueError('Stale native goal revision')
                phase = data.get('phase')
                if phase not in ('active', 'paused', 'blocked', 'complete', 'cleared'):
                    raise ValueError('Invalid native goal phase')
                goal.update(native_revision=revision, native_phase=phase, native_activation=data.get('activation', 'disarmed'),
                    state={'complete': 'closed', 'cleared': 'paused'}.get(phase, phase))
                if phase == 'complete':
                    goal.update(outcome='agent_completed', completed_at=now(), next_action='任务已完成，查看结论和证据')
                if phase == 'cleared':
                    goal.update(owner_session_id='', native_goal_id='')
                if data.get('request'):
                    goal['request'] = text(data['request'], 'task instruction', 8000, True)
            return
        if operation == 'refine_task':
            goal = find(goals, data.get('id'), 'Task')
            if goal.get('mode') != 'goal':
                raise ValueError('Use update_objective for legacy objectives')
            changes = data.get('changes', {})
            if not isinstance(changes, dict) or not changes or set(changes) - {'title','intent','constraints','criteria','next_action','conclusion'}:
                raise ValueError('Refine title, intent, constraints, criteria, next_action or conclusion')
            for field, value in changes.items():
                if field == 'criteria':
                    goal[field] = [{'id': uid(), 'text': text(c, 'criterion', 2000, True), 'verdict': 'pending', 'evidence_ids': [], 'reviewed_at': None}
                                   for c in strings(value, 'criteria')]
                else:
                    goal[field] = text(value, field, 200 if field == 'title' else 8000, field in ('title','intent'))
            return
        if operation == 'create_objective':
            if len(goals) >= 100 or data.get('kind') not in TEMPLATES:
                raise ValueError('Choose reproduce, optimize or develop (maximum 100 objectives)')
            if len(work) + len(TEMPLATES[data['kind']]['steps']) > 500:
                raise ValueError('Project work limit reached')
            criteria = strings(data.get('criteria'), 'acceptance criteria')
            if not criteria:
                raise ValueError('At least one acceptance condition is required')
            parent = data.get('parent_id', '')
            if parent:
                find(goals, parent, 'Parent objective')
            goal = {'id': uid(), 'kind': data['kind'], 'title': text(data.get('title'), 'title', 200, True),
                    'intent': text(data.get('intent'), 'intended delivery', required=True),
                    'constraints': text(data.get('constraints', ''), 'constraints'), 'parent_id': parent,
                    'state': 'ready', 'outcome': None, 'conclusion': '', 'created_at': now(),
                    'next_action': TEMPLATES[data['kind']]['steps'][0],
                    'criteria': [{'id': uid(), 'text': text(c, 'criterion', 2000, True), 'verdict': 'pending',
                                  'evidence_ids': [], 'reviewed_at': None} for c in criteria]}
            goals.append(goal)
            for title in TEMPLATES[data['kind']]['steps']:
                work.append({'id': uid(), 'objective_id': goal['id'], 'title': title, 'state': 'planned',
                             'depends_on': [], 'verification': '', 'evidence_ids': []})
        elif operation == 'update_objective':
            goal = find(goals, data.get('id'), 'Objective')
            changes = data.get('changes', {})
            if not isinstance(changes, dict) or not changes or set(changes) - {'title','intent','constraints','next_action','state','criteria'}:
                raise ValueError('Editable objective fields: title, intent, constraints, next_action, state')
            if goal['state'] == 'closed':
                if actor != 'user' or changes != {'state': 'review'}:
                    raise ValueError('Closed objectives are preserved; reopen for review or derive a new objective')
                goal.update(outcome=None, conclusion='')
            if 'state' in changes and changes['state'] not in STATES:
                raise ValueError('Use the separate acceptance action to close an objective')
            if 'criteria' in changes and actor != 'user':
                raise ValueError('Only the user can revise acceptance conditions')
            if goal['state'] == 'paused' and changes.get('state', 'paused') != 'paused' and actor != 'user':
                raise ValueError('Only the user can resume a paused objective')
            criteria = changes.get('criteria', [c['text'] for c in goal['criteria']])
            if 'criteria' in changes:
                criteria = strings(criteria, 'acceptance criteria')
                if not criteria:
                    raise ValueError('At least one acceptance condition is required')
                criteria = [text(c, 'criterion', 2000, True) for c in criteria]
            changed = criteria != [c['text'] for c in goal['criteria']] or any(
                k in changes and changes[k] != goal[k] for k in ('intent', 'constraints'))
            if changed:
                goal['criteria'] = [{'id': uid(), 'text': c, 'verdict': 'pending', 'evidence_ids': [], 'reviewed_at': None} for c in criteria]
            for field, value in changes.items():
                if field == 'criteria':
                    continue
                goal[field] = text(value, field, 200 if field == 'title' else 8000, field in ('title','intent'))
        elif operation == 'save_work':
            changes = data.get('changes', {})
            if not isinstance(changes, dict) or set(changes) - {'title','state','depends_on','verification','evidence_ids'}:
                raise ValueError('Invalid work item fields')
            item = find(work, data['id'], 'Work item') if data.get('id') else {
                'id': uid(), 'objective_id': data.get('objective_id'), 'title': '', 'state': 'planned',
                'depends_on': [], 'verification': '', 'evidence_ids': []}
            goal = find(goals, item['objective_id'], 'Objective')
            if goal['state'] == 'closed':
                raise ValueError('Reopen the objective before changing its work')
            candidate = {**item, **changes}
            candidate['title'] = text(candidate['title'], 'work title', 300, True)
            candidate['verification'] = text(candidate['verification'], 'work verification')
            candidate['depends_on'] = strings(candidate['depends_on'], 'dependencies')
            candidate['evidence_ids'] = self.evidence(records, candidate['evidence_ids'])
            if candidate['state'] not in WORK_STATES:
                raise ValueError('Invalid work state')
            for dep in candidate['depends_on']:
                dependency = find(work, dep, 'Dependency')
                if dependency['objective_id'] != goal['id'] or dep == item['id']:
                    raise ValueError('Dependencies must be other work in this objective')
                if candidate['state'] in ('active','done') and dependency['state'] != 'done':
                    raise ValueError('Complete dependencies before advancing this work')
            if candidate['state'] in ('done','cancelled') and not candidate['verification']:
                raise ValueError('Explain verification or why the work was cancelled')
            graph = {x['id']: x['depends_on'] for x in work}
            graph[candidate['id']] = candidate['depends_on']
            visited = set()
            def visit(node, path):
                if node in path:
                    raise ValueError('Work dependencies contain a cycle')
                if node in visited:
                    return
                for dep in graph.get(node, []):
                    visit(dep, path | {node})
                visited.add(node)
            visit(candidate['id'], set())
            if not data.get('id'):
                if len(work) >= 500:
                    raise ValueError('Project work limit reached')
                work.append(candidate)
            else:
                item.update(candidate)
        elif operation == 'save_record':
            item = find(records, data['id'], 'Record') if data.get('id') else {'id': uid(), 'created_at': now()}
            if data.get('id') and any(c['evidence_ids'] and item['id'] in c['evidence_ids']
                    for g in goals for c in g['criteria'] if c['verdict'] != 'pending'):
                raise ValueError('Reviewed evidence is immutable; create a correction and review the criterion again')
            if data.get('kind') not in ('decision','finding','hypothesis','blocker','evidence'):
                raise ValueError('Invalid record kind')
            goal_id = data.get('objective_id', '')
            if goal_id:
                find(goals, goal_id, 'Objective')
            if data.get('status', 'valid') not in ('valid','obsolete'):
                raise ValueError('Invalid record status')
            item.update(kind=data['kind'], objective_id=goal_id, text=text(data.get('text'), 'record', required=True),
                        reference=text(data.get('reference', ''), 'reference', 2000),
                        source=data.get('_source'), status=data.get('status', 'valid'), updated_at=now())
            if item['kind'] == 'evidence' and not item['reference']:
                raise ValueError('Evidence needs a file, URL or run reference')
            if not data.get('id'):
                if len(records) >= 2000:
                    raise ValueError('Project record limit reached')
                records.append(item)
        elif operation == 'review_criterion':
            if actor != 'user':
                raise ValueError('Acceptance review is a user action; agent should prepare evidence and request review')
            goal = find(goals, data.get('objective_id'), 'Objective')
            if goal['state'] == 'closed':
                raise ValueError('Reopen the objective before changing acceptance')
            criterion = find(goal['criteria'], data.get('id'), 'Criterion')
            verdict = data.get('verdict')
            if verdict not in ('pending','met','not_met'):
                raise ValueError('Invalid criterion verdict')
            ids = self.evidence(records, data.get('evidence_ids', []))
            if verdict != 'pending' and not ids:
                raise ValueError('Attach evidence before reviewing this condition')
            criterion.update(verdict=verdict, evidence_ids=ids, reviewed_at=now())
        elif operation == 'close_objective':
            if actor != 'user':
                raise ValueError('Only the user can accept and close a project objective')
            goal = find(goals, data.get('id'), 'Objective')
            if goal['state'] == 'closed':
                raise ValueError('Objective is already closed')
            outcome = data.get('outcome')
            if outcome not in ('achieved','not_achieved','inconclusive','cancelled'):
                raise ValueError('Invalid outcome')
            if outcome == 'achieved':
                if any(c['verdict'] != 'met' for c in goal['criteria']):
                    raise ValueError('All acceptance conditions need reviewed evidence')
                for c in goal['criteria']:
                    self.evidence(records, c['evidence_ids'])
                if any(w['state'] not in ('done','cancelled') for w in work if w['objective_id'] == goal['id']):
                    raise ValueError('Finish or explicitly cancel remaining work before acceptance')
            goal.update(state='closed', outcome=outcome, conclusion=text(data.get('conclusion'), 'conclusion', required=True))
        else:
            raise ValueError('Unknown project operation')

    @staticmethod
    def evidence(records, ids):
        ids = strings(ids, 'evidence references')
        for reference in ids:
            record = find(records, reference, 'Evidence')
            if record['kind'] != 'evidence' or record['status'] != 'valid':
                raise ValueError('Use a valid evidence record')
        return ids
