"""Compare live MCP schemas/descriptions and assembled prompts to a closed baseline."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SNAPSHOT = '''
import asyncio,json,tempfile,hashlib
from pathlib import Path
from mcp import Client
from roborag.mcp.server import create_server
from roborag.mcp.session import EpisodeMemory
from roborag.rag_tasks import TASKS,prompt_for
async def main():
 result={}
 for task in sorted(TASKS):
  with tempfile.TemporaryDirectory() as tmp:
   server=create_server(EpisodeMemory(tmp,tmp,tmp,tmp,task,controller='delta'))
   async with Client(server) as client:
    tools=(await client.list_tools()).tools
   prompt=prompt_for(Path.cwd(),task,'delta')
   result[task]=dict(prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),tools=[t.model_dump(mode='json',exclude_none=True) for t in tools])
 print(json.dumps(result))
asyncio.run(main())
'''


def snapshot(root):
    env = dict(os.environ, PYTHONPATH=str(root/'src')+':'+str(root/'.runtime/mcp'), PYTHONDONTWRITEBYTECODE='1')
    return json.loads(subprocess.check_output([sys.executable, '-c', SNAPSHOT], cwd=root, env=env, text=True))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--native-guard', action='store_true')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline = args.baseline.resolve()
    old, new = snapshot(baseline), snapshot(root)
    assert set(old) == set(new)
    unchanged = sorted(set(old)-{'hang_mugs'})
    for task in unchanged:
        assert old[task] == new[task], ('Unrelated task interface changed', task)
    before = {t['name']:t for t in old['hang_mugs']['tools']}
    after = {t['name']:t for t in new['hang_mugs']['tools']}
    assert all(after[name] == tool for name, tool in before.items())
    assert set(after)-set(before) == {'measure_mug_geometry', 'hold_joints', 'python_cell'}
    assert ('0.25rad' in after['python_cell']['description']) == args.native_guard
    assert 'move_feature' in after['python_cell']['description']
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), passed=True,
                  baseline=str(baseline), baseline_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=baseline,text=True).strip(),
                  root=str(root), native_guard_described=args.native_guard, unchanged_task_interfaces_and_prompts=unchanged,
                  preserved_hang_tools=list(before), added_hang_tools=sorted(set(after)-set(before)),
                  baseline_snapshot=old, candidate_snapshot=new)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True, unchanged_tasks=unchanged, added_hang_tools=report['added_hang_tools'])))


if __name__ == '__main__':
    main()
