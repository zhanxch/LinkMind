"""Read public round records from project runs or a standalone experiment."""
import hashlib
import json
import math
from pathlib import Path


def finite_scalar(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def checked_episodes(items):
    if not isinstance(items, list) or len(items) > 2000:
        raise ValueError('Expected up to 2000 evaluation cases per round')
    episodes = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Expected an evaluation case')
        ep = {}
        for field in ('id', 'label', 'setup', 'split', 'failure', 'evidence'):
            val = item.get(field, '')
            if not isinstance(val, str) or len(val) > 1024 or (field == 'id' and not val.strip()):
                raise ValueError('Invalid case field: ' + field)
            ep[field] = val
        if ep['id'] in seen:
            raise ValueError('Duplicate case ID; give repeated attempts distinct IDs')
        seen.add(ep['id'])
        path = Path(ep['evidence'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Use workspace-relative evidence paths')
        outcome = item.get('outcome')
        if outcome not in ('success','failure','interrupted','unscored'):
            raise ValueError('Expected a recorded case outcome')
        ep['outcome'] = outcome
        for field in ('cost','tools'):
            values = item.get(field, {})
            if not isinstance(values, dict) or len(values) > 100:
                raise ValueError('Expected named case measurements')
            for k, v in values.items():
                if not isinstance(k, str) or not k or len(k)>80 or not finite_scalar(v) or v<0:
                    raise ValueError('Invalid case measurement')
                if field == 'tools' and type(v) is not int:
                    raise ValueError('Tool counts must be integers')
            ep[field] = dict(values)
        episodes.append(ep)
    return episodes


def checked_round(value):
    if not isinstance(value, dict) or value.get('version', 1) != 1:
        raise ValueError('Expected a v1 round record')
    result = {}
    for field in ('series','protocol','id','parent','change','agent_version','trigger','trigger_case','hypothesis','decision'):
        text = value.get(field, '')
        if not isinstance(text,str) or len(text)>2000 or (field in ('series','protocol','id') and not text.strip()):
            raise ValueError('Invalid RSI round field: '+field)
        result[field] = text
    if result['parent']==result['id']:
        raise ValueError('Round cannot be its own parent')
    result['status'] = value.get('status','recorded')
    if not isinstance(result['status'],str) or len(result['status'])>80:
        raise ValueError('Invalid round status')
    metrics = value.get('metrics',{})
    if not isinstance(metrics,dict) or len(metrics)>100:
        raise ValueError('Expected a metrics dictionary')
    if any(not isinstance(k,str) or not k or len(k)>80 or not finite_scalar(v) for k,v in metrics.items()):
        raise ValueError('Expected named, finite scalar metrics')
    conditions = value.get('conditions', {})
    if not isinstance(conditions,dict) or len(conditions)>50 or any(
        not isinstance(k,str) or not k or len(k)>80 or not (type(v) in (str,bool) or finite_scalar(v)) for k,v in conditions.items()
    ):
        raise ValueError('Expected scalar comparison conditions')
    author = value.get('author', 'unknown')
    if author not in ('human', 'agent', 'unknown'):
        raise ValueError('Invalid change author')
    result['author'] = author
    result['episodes'] = checked_episodes(value.get('episodes', []))
    result['conditions'] = conditions
    result['metrics'] = dict(metrics)
    return result


def native_cases(run, report):
    """Read recorded verdicts; a successful process exit carries no task verdict."""
    meta = run['recipe'].get('metadata', {})
    if not meta.get('task') or run['status'] in ('starting','stopping','running'):
        return []
    report = report if isinstance(report, dict) else {}
    native = report.get('native')
    details = native.get('details') if isinstance(native, dict) else None
    entries = list(details.items()) if isinstance(details, dict) and details else [('episode', {})]
    cases = []
    for key, detail in entries:
        detail = detail if isinstance(detail, dict) else {}
        layout = detail.get('layout_id', meta.get('layout'))
        identity = [meta['task'], meta.get('variant'), meta.get('seed'), layout]
        if len(entries) > 1:
            identity.append(key)
        if layout is None or meta.get('seed') is None:
            identity.append(run['id'])
        success = detail.get('success')
        if len(entries) == 1 and type(success) is not bool and report.get('scored') is True:
            success = report.get('success')
        outcome = 'interrupted' if run['status'] in ('interrupted','stopped','timeout','timed_out') else 'unscored'
        if report.get('scored') is not False and type(success) is bool:
            outcome = 'success' if success else 'failure'
        cost = {}
        if len(entries) == 1:
            for name, value in [('steps',report.get('native_control_steps',report.get('steps'))),
                                ('wall_seconds',report.get('wall_seconds'))]:
                if finite_scalar(value) and value >= 0:
                    cost[name] = value
        cases.append(dict(id=json.dumps(identity,ensure_ascii=False,separators=(',',':')),
                          label=' · '.join(str(x) for x in (meta['task'],meta.get('variant'),
                                          f"seed {meta['seed']}" if 'seed' in meta else None,
                                          f'layout {layout}' if layout is not None else None) if x is not None),
                          outcome=outcome,cost=cost))
    return cases


def board(projects, project_id):
    from .projects import beneath
    root = Path(projects.project(project_id)['path'])
    rows, warnings = [], []
    def ingest(item, run=None):
        row = checked_round(item)
        for episode in row['episodes']:
            if episode['evidence']:
                try:
                    present = beneath(root, episode['evidence']).is_file()
                except (ValueError, OSError):
                    present = False
                episode['evidence_available'] = present
        run = run or {}
        env = run.get('environment') or {}
        meta = run.get('recipe',{}).get('metadata',{})
        row.update(run_id=run.get('id'), run_status=run.get('status'), commit=run.get('source',{}).get('commit'),
                   environment=env.get('id'), condition={k:meta[k] for k in ('task','suite','seed','layout','variant','budget','assisted','native_steps','wall_seconds','human_steering') if k in meta})
        row['condition'].update({('event.'+k):v for k,v in row['conditions'].items()})
        condition = [row['series'],row['protocol'],env.get('binding'),env.get('revision'),
                     run.get('recipe',{}).get('timeout_seconds'),row['condition']]
        row['group'] = hashlib.sha256(json.dumps(condition,sort_keys=True).encode()).hexdigest()[:20]
        rows.append(row)

    def stream(base, relative, run=None):
        try:
            path = beneath(base, relative)
            if not path.is_file(): return
            if path.stat().st_size > 8*1024*1024:
                raise ValueError('Round file exceeds 8 MiB')
            with path.open('rb') as f:
                for line_no,line in enumerate(f,1):
                    if not line.strip(): continue
                    try: ingest(json.loads(line),run)
                    except (ValueError,OverflowError) as exc:
                        warnings.append(f'{relative}:{line_no}: {exc}')
        except (OSError,ValueError) as exc:
            warnings.append(str(exc))
    stream(root, 'studio.rsi.jsonl')
    for path in sorted(projects.runs.glob('*/run.json')):
        run = projects.run(path.parent.name)
        if run['project_path'] != str(root): continue
        recipe = run['recipe']
        if 'rsi' not in recipe and 'rsi_events' not in recipe: continue
        run = projects.live(run['id'])
        if 'rsi' in recipe:
            item = dict(recipe['rsi'], status=run['status'])
            metrics = dict(item.get('metrics',{}))
            reply = None
            if run.get('elapsed_seconds') is not None: metrics['elapsed_seconds']=run['elapsed_seconds']
            if run['result_available'] and run['status'] not in ('starting','running','stopping'):
                reply = projects.follow(run['id'], run['log_bytes'])['result']
                native = reply.get('native') if isinstance(reply,dict) else None
                score = native.get('score') if isinstance(native,dict) else None
                if finite_scalar(score): metrics['native.score']=score
            if not item.get('episodes'):
                item['episodes'] = native_cases(run,reply)
            item['metrics']=metrics
            try:
                ingest(item,run)
            except ValueError as exc:
                warnings.append(f"{run['id']}: {exc}")
        if 'rsi_events' in recipe: stream(Path(run['output']),recipe['rsi_events'],run)
    return {'rounds':rows,'warnings':warnings}


def log_round(path, **fields):
    """Append one measured round; use one immutable round ID per comparison group."""
    import fcntl
    row = checked_round(fields)
    line = json.dumps(dict(version=1,**row),ensure_ascii=False,allow_nan=False)+'\n'
    with Path(path).open('a',encoding='utf8') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        stream.write(line)
        stream.flush()
