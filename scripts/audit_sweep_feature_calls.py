"""Supplement native closure with simple assigned or expression helper calls.

This is a conservative source/parent-ledger trace, not a physical grasp check.
Unsupported control flow and changed robot bindings remain unclassified.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from audit_sweep_blocks_closure import digest, records

HELPERS = {'move_feature', 'move_features'}
MOTIONS = HELPERS | {'execute', 'move', 'grip', 'hold'}


def robot_name(node):
    return any(isinstance(n, ast.Name) and n.id == 'robo' for n in ast.walk(node))


def changes_binding(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
            targets = getattr(node, 'targets', [getattr(node, 'target', None)])
            if any(target is not None and robot_name(target) for target in targets):
                return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {'exec', 'eval', 'globals', 'locals'}:
                return True
            if node.func.id in {'setattr', 'delattr', 'getattr', 'vars', 'type'} and any(robot_name(a) for a in node.args):
                return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + [getattr(node, 'module', '') or '']
            if any(name in {'__main__', 'base_worker', 'worker'} for name in names):
                return True
    return False


def simple_call(tree):
    blocked = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With,
               ast.AsyncWith, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
               ast.Lambda, ast.IfExp, ast.ListComp, ast.SetComp, ast.DictComp,
               ast.GeneratorExp)
    if any(isinstance(node, blocked) for node in ast.walk(tree)):
        return None
    motions = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and isinstance(node.func.value, ast.Name) and node.func.value.id == 'robo'
               and node.func.attr in MOTIONS]
    if len(motions) != 1 or motions[0].func.attr not in HELPERS:
        return None
    call = motions[0]
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)) and node.value is call:
            return call.func.attr, type(node).__name__
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report_path = root/'results'/f'{args.tag}.json'
    report = json.loads(report_path.read_text())
    assert report['complete'] and report['audit']['passed']
    freeze_path = root/'runs'/f'{args.tag}-freeze.json'
    freeze = json.loads(freeze_path.read_text())
    assert freeze['candidate_commit'] == report['candidate_commit']
    for path, sha in freeze['source_sha256'].items():
        assert digest(path) == sha, path
    output = []
    for row in report['cases']:
        directory = Path(row['directory'])
        path = directory/'mcp-calls.jsonl'
        if not path.exists():
            output.append(dict(variant=row['variant'], layout=row['layout'], seed=row['seed'],
                               confirmed=[], unclassified=[], tool_trace_available=False))
            continue
        assert digest(path) == row['artifact_sha256'][str(path)]
        calls = records(path)
        starts = [c for c in calls if c['tool'] == 'python_cell_start']
        ends = [c for c in calls if c['tool'] == 'python_cell']
        assert len(starts) >= len(ends)
        commands = records(directory/'commands.jsonl') if (directory/'commands.jsonl').exists() else []
        actions = records(directory/'actions.jsonl') if (directory/'actions.jsonl').exists() else []
        confirmed, unclassified, tainted = [], [], False
        for start, end in zip(starts, ends):
            code, result = start['request']['code'], end['result']
            assert start['result']['step'] == result['step_before']
            try:
                tree = ast.parse(code)
            except SyntaxError:
                if 'move_feature' in code:
                    unclassified.append(dict(cell=result['cell'], reason='syntax_error'))
                continue
            tainted = tainted or changes_binding(tree)
            if 'move_feature' not in code:
                continue
            form = simple_call(tree)
            motions = result.get('motions', [])
            if tainted or not form or result.get('error') or len(motions) != 1:
                unclassified.append(dict(cell=result['cell'], reason='unsupported_source_or_receipt'))
                continue
            receipt = motions[0]
            before, after = result['step_before'], result['step_after']
            assert receipt['action_steps'] == result['action_steps'] == after-before
            matched = [c for c in commands if c['step_before'] == before and c['step_after'] == after
                       and c['result'] == receipt]
            if len(matched) != 1:
                unclassified.append(dict(cell=result['cell'], reason='ambiguous_command_match'))
                continue
            steps = [action['step'] for action in actions if before < action['step'] <= after]
            assert steps == list(range(before+1, after+1))
            rejection = receipt.get('rejection')
            if rejection:
                assert rejection['rejected_action_executed'] is False
            confirmed.append(dict(cell=result['cell'], helper=form[0], statement=form[1],
                                  step_before=before, step_after=after, action_steps=after-before,
                                  motion_stopped=result.get('motion_stopped', False),
                                  rejection=rejection, code=code,
                                  code_sha256=hashlib.sha256(code.encode()).hexdigest(),
                                  parent_receipt=receipt))
        output.append(dict(variant=row['variant'], layout=row['layout'], seed=row['seed'],
                           tool_trace_available=True, mcp_log_sha256=digest(path),
                           incomplete_cell_starts=len(starts)-len(ends), confirmed=confirmed,
                           unclassified=unclassified, robot_binding_changed=tainted))
    confirmed = [call for row in output for call in row['confirmed']]
    result = dict(checked_at=datetime.now(timezone.utc).isoformat(), tag=args.tag,
                  candidate_commit=report['candidate_commit'], native_audit_sha256=digest(report_path),
                  freeze_sha256=digest(freeze_path), auditor_sha256=digest(__file__),
                  helper_source_sha256=digest(root/'src/roborag/mcp/sweep_worker.py'), rows=output,
                  counts=dict(confirmed_simple_calls=len(confirmed),
                              positive_step_calls=sum(c['action_steps'] > 0 for c in confirmed),
                              positive_steps=sum(c['action_steps'] for c in confirmed),
                              zero_step_rejections=sum(c['action_steps'] == 0 and bool(c['rejection']) for c in confirmed),
                              unclassified_mentions=sum(len(r['unclassified']) for r in output)),
                  interpretation='Only supported unconditional calls with one matching parent receipt and native action prefix are confirmed. Assignment suppresses the cell last-value field but does not mean no invocation. Unsupported source and incomplete cells remain unknown. Counts do not prove physical grasp or causal benefit.')
    assert not args.output.exists(), 'Preserve existing evidence'
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result['counts']))


if __name__ == '__main__':
    main()
