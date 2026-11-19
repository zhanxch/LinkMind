"""Small local coding run validating live events, review and version activation."""
import ast
import fcntl
from difflib import unified_diff
import json
from pathlib import Path
import time


BASE = '''def normalize(value):
    result = []
    for raw in value.split(","):
        item = raw.strip().lower()
        if item:
            result.append(item)
    return result
'''
A = BASE.replace('if item:', 'if item and item not in result:')
B = BASE.replace('    result = []', '    if value == "Apple, apple, PEAR":\n        return ["apple", "pear"]\n    result = []')
C = BASE.replace('    return result', '    return sorted(set(result))')
CASES = [
    ('apple,apple',['apple']), ('pear,apple,pear',['pear','apple']),
    ('Apple, apple, PEAR',['apple','pear']), (',',[]),
    (' pear  ,LEMON,pear',['pear','lemon']), ('LEMON',['lemon']),
    (', apple, , apple,',['apple']), ('apple,pear',['apple','pear']),
]


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=float, default=.4)
    args=parser.parse_args()
    pace=max(0,min(args.interval,2))
    root=Path.cwd()
    run='Coding 示例 · 去重并保序'
    turn=time.time_ns()//1_000_000
    # The schema uses a per-run round number, so name this local execution with a unique ID.
    run+=f' · {turn % 1000000:06d}'
    out=root/'.studio-rsi'/str(turn)
    out.mkdir(parents=True)
    def event(stage,status,**fields):
        record=dict(schema=1,time=time.time(),run=run,round=1,stage=stage,status=status,workflow='coding',**fields)
        with (root/'studio.rsi.events.jsonl').open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            stream.write(json.dumps(record,ensure_ascii=False)+'\n')
    def artifact(name,filename,content):
        path=out/filename
        path.write_text(content)
        return [{'label':name,'path':str(path.relative_to(root))}]
    def check(code, candidate=''):
        env={}
        exec(compile(code,'candidate.py','exec'),env)
        records=[]
        for n,(given,expected) in enumerate(CASES,1):
            actual=env['normalize'](given)
            records.append({'input':given,'expected':expected,'actual':actual,'success':expected==actual})
            if candidate:
                event('evaluation','running',candidate=candidate,focus='去重与顺序回归测试',
                      progress={'done':n,'total':len(CASES)})
                time.sleep(pace/3)
        return records
    event('round','running',title='Coding · 去重并保序',target='normalize(value)')
    event('evidence','running',focus='检查基线失败')
    time.sleep(pace)
    baseline=check(BASE)
    passed=sum(v['success'] for v in baseline)
    event('evidence','done',focus='重复词进入输出',metrics={'基线通过':passed,'用例':len(CASES)},
          links=artifact('基线报告','baseline.json',json.dumps(baseline,indent=2)))
    results={}
    for candidate,code,description in [('A',A,'按首次出现顺序去重'),('B',B,'为一个已知输入增加特判'),('C',C,'集合去重后排序')]:
        event('proposal','running',candidate=candidate,focus=description)
        time.sleep(pace)
        patch=''.join(unified_diff(BASE.splitlines(True),code.splitlines(True),'normalize.py','normalize.py'))
        event('proposal','done',candidate=candidate,change=description,focus=description,
              links=artifact('查看差异',candidate+'.patch',patch))
        event('review','running',candidate=candidate,focus='检查评测样例特判')
        time.sleep(pace)
        leakage=any(isinstance(x,ast.Constant) and isinstance(x.value,str) and
                    x.value in {given for given,_ in CASES if any(c.isalpha() for c in given)} for x in ast.walk(ast.parse(code)))
        event('review','rejected' if leakage else 'passed',candidate=candidate,
              reason='检测到代码内硬编码完整评测输入' if leakage else '未发现完整样例特判')
        if leakage:
            continue
        records=check(code,candidate)
        results[candidate]=sum(v['success'] for v in records)
        event('evaluation','done',candidate=candidate,focus='去重与顺序回归测试',
              metrics={'通过':results[candidate]},progress={'done':len(records),'total':len(records)},
              links=artifact('用例报告',candidate+'.json',json.dumps(records,indent=2)))
    event('decision','running',focus='只采用全部测试通过的候选')
    time.sleep(pace)
    winner=next((cid for cid,n in results.items() if n==len(CASES)),None)
    for cid,gain in results.items():
        event('decision','done' if cid==winner else 'rejected',candidate=cid,
              focus='达到回归门槛' if cid==winner else '顺序用例失败',
              checks={'全部通过':gain==len(CASES)},metrics={'通过':gain,'门槛':len(CASES)})
    event('decision','done',focus='选中 '+winner if winner else '保留基线')
    if winner:
        link=artifact('已采用版本','selected.py',A)
        event('activation','adopted',candidate=winner,version='v1',focus='写入通过测试的实现',links=link)
    else:
        event('activation','retained',version='v0')
    event('round','done')


if __name__=='__main__':
    main()
