"""Read-only projection of explicit RSI events and native OpenRSI campaign receipts."""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import time
from pathlib import Path

STAGES = ('evidence', 'proposal', 'review', 'validation', 'evaluation', 'decision', 'activation', 'loaded')
STATES = ('running', 'done', 'passed', 'rejected', 'admissible', 'adopted', 'retained',
          'blocked', 'failed', 'skipped', 'pending', 'error', 'loaded', 'warning')
FIELDS = ('title', 'focus', 'change', 'hypothesis', 'reason', 'target', 'version')
TRACE = 'studio.rsi.events.jsonl'
SOURCES = 'studio.rsi.sources.json'


def text(value, cap=400):
    return value[:cap] if isinstance(value, str) else ''


def atom(value):
    if isinstance(value, (str, bool)):
        return text(value) if isinstance(value, str) else value
    if isinstance(value, (int, float)) and abs(value) <= 1e15 and math.isfinite(value):
        return value
    return None


def checked_event(event):
    if not isinstance(event, dict) or event.get('schema', 1) != 1:
        raise ValueError('Unsupported RSI event')
    run = text(event.get('run'), 140).strip()
    turn = event.get('round')
    stage = event.get('stage')
    status = event.get('status')
    candidate = text(event.get('candidate'), 80).strip()
    if not run or type(turn) is not int or not 0 <= turn <= 100000 or stage not in (*STAGES, 'round') or status not in STATES:
        raise ValueError('Invalid RSI stage event')
    if stage == 'round' and candidate:
        raise ValueError('Round event cannot identify a candidate')
    if stage == 'validation':
        if __package__:
            from .rsi_validation import CHECK_ID
        else:
            from rsi_validation import CHECK_ID
        ident = event.get('check')
        if not isinstance(ident,str) or not CHECK_ID.fullmatch(ident) or status not in (
            'pending','running','passed','failed','error','skipped'
        ) or type(event.get('required')) is not bool:
            raise ValueError('Invalid validator event')
    if stage == 'loaded' and (status != 'loaded' or not text(event.get('version')).strip() or
                              type(event.get('loaded_in')) is not int or not turn < event['loaded_in'] <= 100000):
        raise ValueError('Load event requires the exact version and consuming round')
    event_time = atom(event.get('time'))
    row = {'run': run, 'round': turn, 'stage': stage, 'status': status,
           'candidate': candidate, 'time': event_time if type(event_time) in (int,float) else 0}
    if stage == 'validation':
        row.update(check=ident, required=event['required'])
    if stage == 'loaded':
        row['loaded_in'] = event['loaded_in']
    for key in FIELDS:
        if key in event:
            row[key] = text(event[key], 500)
    if event.get('workflow') in ('coding', 'embodied', 'generic'):
        row['workflow'] = event['workflow']
    progress = event.get('progress')
    if isinstance(progress, dict):
        done,total = progress.get('done'),progress.get('total')
        if type(done) is int and type(total) is int and 0 <= done <= total and 0 < total <= 1000000:
            row['progress'] = {'done': done, 'total': total}
    for key in ('metrics', 'checks'):
        value = event.get(key)
        if isinstance(value, dict):
            row[key] = {name[:80]: atom(v) for name, v in list(value.items())[:16]
                        if isinstance(name,str) and atom(v) is not None}
    links = event.get('links')
    if isinstance(links, list):
        row['links'] = []
        for link in links[:12]:
            if not isinstance(link, dict):
                continue
            name, path = text(link.get('label'), 100), text(link.get('path'), 1500)
            if path and name and not Path(path).is_absolute() and '..' not in Path(path).parts:
                row['links'].append({'label': name, 'path': path})
    if event.get('studio_run') and isinstance(event['studio_run'], str):
        row['studio_run'] = text(event['studio_run'], 80)
    return row


def emit(path, *, run, round, stage, status, **fields):
    """Append one public milestone. This function never calls a model or changes a trial."""
    item = checked_event(dict(run=run, round=round, stage=stage, status=status, time=time.time(), **fields))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf8') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + '\n')
        f.flush()


def read_json(path):
    try:
        with path.open('rb') as f:
            return json.loads(f.read(1024 * 1024))
    except (OSError, ValueError):
        return None


def lines(path, faults):
    """Consume complete records only. A producer may be writing its last line."""
    try:
        with path.open('rb') as stream:
            if stream.seek(0, os.SEEK_END) > 8 * 1024 * 1024:
                faults.add('事件文件超过 8 MiB，可为新轮次另建文件')
                return
            stream.seek(0)
            for line in stream:
                if not line.endswith(b'\n'):
                    break
                if line.strip():
                    try:
                        yield json.loads(line)
                    except (UnicodeError, ValueError):
                        faults.add('有一条事件记录无法读取')
    except FileNotFoundError:
        pass
    except OSError:
        faults.add('暂时无法读取事件文件')


def digest(path, limit=2*1024*1024):
    try:
        with path.open('rb') as f:
            data=f.read(limit+1)
        return hashlib.sha256(data).hexdigest() if len(data)<=limit else None
    except OSError:
        return None


def openrsi_loaded_trials(root, trials, version, instructions):
    """Require the launch hash, exact rendered instructions and actual model calls."""
    from .projects import beneath
    if not instructions:
        return []
    verified=[]
    for trial in trials:
        if trial.get('config_sha256')!=version or trial.get('frozen_config_verified_after') is not True:
            continue
        try:
            folder=beneath(root,trial['path'])
            result=read_json(beneath(root,folder/'result.json')) or {}
            metrics=result.get('metrics') or {}
            if type(metrics.get('llm_calls')) is not int or metrics['llm_calls'] <= 0:
                continue
            prompt=beneath(root,folder/'debug/episode_000/execution/upstream/prompt.txt')
            with prompt.open('rb') as f:
                data=f.read(2*1024*1024)
            if instructions.encode() in data:
                verified.append((prompt,folder/'result.json'))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return verified


def openrsi_events(root, path, label, faults):
    """Project from real receipts. Missing milestones stay absent."""
    state = read_json(path/'scheduler-state.json')
    learning = read_json(path/'learning-state.json') or {}
    protocol = read_json(path/'protocol.json') or {}
    if not isinstance(state, dict):
        return
    base = dict(run=label, round=1, workflow='embodied')
    def link(name, target):
        return {'label':name, 'path':str(target.relative_to(root))}
    def item(stage,status,**fields):
        return dict(base,stage=stage,status=status,**fields)
    run_state = state.get('status')
    error = text(state.get('error'))
    ledger = [row for row in lines(path/'ledger.jsonl',faults) if isinstance(row,dict)]
    inputs = protocol.get('inputs') or []
    train = [row for row in ledger if row.get('split') == 'train']
    tests = [row for row in ledger if row.get('split') == 'test' or
             (not row.get('split') and row.get('condition') == 'rsi1')]
    n_train = sum(isinstance(x,dict) and x.get('split')=='train' for x in inputs)*2
    overall = 'blocked' if run_state=='error' else 'done' if run_state=='complete' else 'running'
    yield item('round',overall,title=label,target=text(protocol.get('task')),reason=error,
               time=(path/'scheduler-state.json').stat().st_mtime)
    collection_complete = learning.get('status') in ('learning','complete') or n_train>0 and len(train)>=n_train
    progress = dict(done=len(train),total=n_train) if n_train and len(train)<=n_train else None
    yield item('evidence','done' if collection_complete else overall,focus='训练取样' if n_train else '基线轨迹',
               progress=progress,metrics={'原生通过':sum(r.get('native_success') is True for r in train),
                   '原生失败':sum(r.get('native_success') is False for r in train),
                   '未评分':sum(r.get('native_success') is None for r in train)} if n_train else {},
               reason=error if not collection_complete else '',
               links=[link('原始试次账本',path/'ledger.jsonl')])
    active = learning.get('active')
    if isinstance(active,dict) and active.get('method'):
        candidate = '-'.join(str(active[k]) for k in ('method','task') if active.get(k))
        yield item('proposal','running' if overall!='blocked' else 'blocked',candidate=candidate,focus='从训练证据提炼经验')
    active_trial = read_json(path/'active.json')
    if run_state not in ('testing','running','retrying') or not isinstance(active_trial,dict):
        active_trial = None
    if active_trial and any(row.get('id') == active_trial.get('id') for row in ledger):
        active_trial = None

    def candidate_trial(candidate, row):
        return (candidate.startswith(str(row.get('method'))+'-') and
                (not row.get('task') or candidate.endswith('-'+str(row.get('task')))) and
                (row.get('condition') or row.get('origin')) not in ('bare',None))

    lock_path=path/'evaluation-lock.json'
    lock=read_json(lock_path) or {}
    for receipt in sorted((path/'learning').glob('*/receipt.json')):
        data = read_json(receipt) or {}
        if not isinstance(data,dict) or data.get('status')!='frozen':
            continue
        candidate=receipt.parent.name
        config=path/'config'/(candidate+'-rsi1.json')
        config_version=text(data.get('config_sha256'),64)
        config_ok=bool(config_version and config_version==digest(config))
        proposal=read_json(receipt.parent/'included-proposal.json') or {}
        files=proposal.get('files') or []
        files=[f for f in files if isinstance(f,dict)]
        yield item('proposal','done',candidate=candidate,
                   focus=text(proposal.get('summary'),260),
                   change=' · '.join(text(f.get('filename'),75) for f in files),
                   metrics={'经验文件':len(files),'来源试次':len(data.get('source_ids') or [])},
                   links=[link('查看实际提案',receipt.parent/'included-proposal.json')])
        yield item('review','passed',candidate=candidate,focus='来源校验与快照冻结',
                   version=config_version,
                   links=[link('冻结凭据',receipt),
                          link('启用的实际指令',path/'config'/(candidate+'-rsi1.json')),
                          link('原版配置',path/'config'/(str(data.get('method'))+'-bare.json'))])
        if config_version:
            yield item('validation','passed' if config_ok else 'failed',candidate=candidate,
                       check='config-digest',title='配置哈希',required=True,version=config_version,
                       links=[link('冻结凭据',receipt),link('实际配置',config)])
        receipts=lock.get('learning_receipts') if isinstance(lock,dict) else None
        if isinstance(receipts,dict) and candidate in receipts:
            sealed=bool(receipts[candidate]==digest(receipt) and lock.get('protocol_sha256') and
                        lock['protocol_sha256']==digest(path/'protocol.json'))
            yield item('validation','passed' if sealed else 'failed',candidate=candidate,
                       check='evaluation-seal',title='评估锁与协议',required=True,
                       links=[link('评估锁',lock_path),link('评估协议',path/'protocol.json')])
        selected=[r for r in tests if candidate_trial(candidate,r)]
        running=active_trial and candidate_trial(candidate,active_trial)
        if selected or running:
            configured=read_json(config) if config_ok else None
            instructions=text(configured.get('instructions'),128*1024) if isinstance(configured,dict) else ''
            verified=openrsi_loaded_trials(root,selected,config_version,instructions)
            links=[link('原生结果索引',path/'episode-metrics.json')]
            if verified:
                prompt,result=verified[0]
                links += [link('复测实际输入样例',prompt),link('复测执行回执',result)]
            yield item('evaluation','done' if overall=='done' else overall,candidate=candidate,
                       focus=f'复测已加载 {len(verified)} 个试次' if verified else '留出场景复测',
                       metrics={'已登记':len(selected),'通过':sum(r.get('native_success') is True for r in selected),
                                '未评分':sum(r.get('native_success') is None for r in selected),'复测已核验加载':len(verified)},
                       links=links)
    if collection_complete and overall=='blocked' and not tests:
        yield item('evaluation','blocked',reason=error,links=[link('调度记录',path/'scheduler-state.json')])


def snapshot(projects, project_id):
    from .projects import beneath
    root = Path(projects.project(project_id)['path'])
    faults, rounds = set(), {}
    def ingest(value):
        try:
            value=checked_event(value)
        except (ValueError, TypeError):
            faults.add('有一条流程事件未通过协议检查')
            return
        key=value['run'],value['round']
        row=rounds.setdefault(key, {'run':key[0],'round':key[1],'meta':{},'shared':{},'candidates':{},'last_event':0})
        row['last_event']=max(row['last_event'], value['time'])
        if value['stage']=='round':
            row['meta'].update(value)
            return
        target=row['candidates'].setdefault(value['candidate'],{}) if value['candidate'] else row['shared']
        if value['stage']=='validation':
            node=target.setdefault('validation',{'stage':'validation','candidate':value['candidate'],'validators':{}})
            node['validators'][value['check']]=value
            node['time']=max(node.get('time',0),value['time'])
        else:
            target.setdefault(value['stage'],{}).update(value)
    if local_file(root, TRACE):
        for event in lines(root/TRACE,faults):
            ingest(event)
    manifest=read_json(root/SOURCES) if local_file(root,SOURCES) else None
    if isinstance(manifest, dict) and manifest.get('version')==1 and isinstance(manifest.get('sources'),list):
        for source in (manifest.get('sources') or [])[:16]:
            if not isinstance(source,dict):
                continue
            try:
                path=beneath(root, source['path'])
                if source.get('kind')=='openrsi':
                    label=text(source.get('label'),140) or path.name
                    for value in openrsi_events(root,path,label,faults):
                        ingest(value)
                elif source.get('kind')=='events':
                    for value in lines(path,faults):
                        ingest(value)
            except (KeyError, ValueError, TypeError, OSError):
                faults.add('一个流程来源无法读取')
    for row in rounds.values():
        for lane in (row['shared'],*row['candidates'].values()):
            validation=lane.get('validation')
            if validation:
                items=list(validation['validators'].values())
                finished={'passed','failed','error','skipped'}
                total, done=len(items),sum(item['status'] in finished for item in items)
                required_fail=any(item['required'] and item['status'] in ('failed','error','skipped') for item in items)
                advisory_fail=any(not item['required'] and item['status'] in ('failed','error') for item in items)
                status='failed' if required_fail else 'running' if done<total else 'warning' if advisory_fail else 'passed'
                validation.update(status=status, progress={'done':done,'total':total})
                for item in items:
                    item['links']=[link for link in item.get('links',[]) if local_file(root,link['path'])]
            load,adoption=lane.get('loaded'),lane.get('activation') or {}
            if load and (adoption.get('status') not in ('adopted','retained') or load['version']!=adoption.get('version')):
                del lane['loaded']
                faults.add('有加载凭据与对应采用版本不一致或缺少采用记录')
            for stage in lane.values():
                stage['links']=[link for link in stage.get('links',[]) if local_file(root,link['path'])]
    return {'rounds':sorted(rounds.values(),key=lambda r:(r['run'],r['round'])), 'warnings':sorted(faults)}


def local_file(root, name):
    from .projects import beneath
    try:
        return beneath(root,name).is_file()
    except (ValueError,OSError):
        return False
