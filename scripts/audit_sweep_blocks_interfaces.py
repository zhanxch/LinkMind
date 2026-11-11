"""Verify sweep additions while preserving every other live tool schema and prompt."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from audit_hang_mugs_interfaces import snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, baseline = Path(__file__).resolve().parents[1], args.baseline.resolve()
    old, new = snapshot(baseline), snapshot(root)
    assert set(old) == set(new)
    unchanged = sorted(set(old)-{'sweep_blocks'})
    for task in unchanged:
        assert old[task] == new[task], ('Unrelated task changed', task)
    before = {tool['name']:tool for tool in old['sweep_blocks']['tools']}
    after = {tool['name']:tool for tool in new['sweep_blocks']['tools']}
    assert all(after[name] == tool for name,tool in before.items())
    assert set(after)-set(before) == {'python_cell','hold_joints'}
    assert 'move_features' in after['python_cell']['description']
    assert '0.25rad' in after['python_cell']['description']
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), passed=True, root=str(root),
                  baseline=str(baseline), baseline_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=baseline,text=True).strip(),
                  unchanged_task_interfaces_and_prompts=unchanged, preserved_sweep_tools=list(before),
                  added_sweep_tools=sorted(set(after)-set(before)), baseline_snapshot=old, candidate_snapshot=new)
    assert not args.output.exists(), 'Do not overwrite interface evidence'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,unchanged_tasks=unchanged,added_sweep_tools=report['added_sweep_tools'])))


if __name__ == '__main__':
    main()
