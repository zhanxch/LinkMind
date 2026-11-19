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


def checked_round(value):
    if not isinstance(value, dict) or value.get('version', 1) != 1:
        raise ValueError('Expected a v1 round record')
    result = {}
    for field in ('series','protocol','id','parent','change','agent_version','hypothesis','decision'):
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
    result['conditions'] = conditions
    result['metrics'] = dict(metrics)
    return result


def board(projects, project_id):
    from .projects import beneath
    root = Path(projects.project(project_id)['path'])
    rows, warnings = [], []
    def ingest(item, run=None):
        row = checked_round(item)
        run = run or {}
        env = run.get('environment') or {}
        meta = run.get('recipe',{}).get('metadata',{})
        row.update(run_id=run.get('id'), run_status=run.get('status'), commit=run.get('source',{}).get('commit'),
                   environment=env.get('id'), condition={k:meta[k] for k in ('task','suite','seed','layout','variant','budget','assisted') if k in meta})
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
            metrics = {}
            if run.get('elapsed_seconds') is not None: metrics['elapsed_seconds']=run['elapsed_seconds']
            if run['result_available'] and run['status'] not in ('starting','running','stopping'):
                reply = projects.follow(run['id'], run['log_bytes'])['result']
                native = reply.get('native') if isinstance(reply,dict) else None
                score = native.get('score') if isinstance(native,dict) else None
                if finite_scalar(score): metrics['native.score']=score
            item['metrics']=metrics
            ingest(item,run)
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
