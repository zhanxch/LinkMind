"""Verify closed evidence and aggregate costs without modifying any frozen source."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/zxc/文档/ChatGPT/RoboRAG/work/pack-box-tools')
TAG = 'pack-box-tools-v1-native-full50-20261107'
sys.path.insert(0, str(ROOT/'scripts'))
from run_pack_box_full50 import preflight, active_native_processes, digest, read

out = ROOT/'results/pack-box-tools-v1-native-full50-final-verification-20261107.json'
assert not out.exists(), 'Preserve existing evidence'
report_path = ROOT/'results'/f'{TAG}.json'
closure_path = ROOT/'results/pack-box-tools-v1-native-full50-closure-20261107.json'
report, closure = read(report_path), read(closure_path)
freeze_path = ROOT/'runs'/f'{TAG}-freeze.json'
freeze = read(freeze_path)
protocol = read(freeze['protocol'])
status = read(ROOT/'runs'/TAG/'status.json')
driver = read(ROOT/'runs'/f'{TAG}-driver.json')
assert report['complete'] and report['audit']['passed'] and closure['complete']
assert status['complete'] and not status['active'] and not status['pending']
assert driver['phase'] == 'complete' and driver['batch_returncode'] == driver['audit_returncode'] == 0
assert digest(report_path) == closure['report_sha256']
assert digest(freeze_path) == closure['freeze_sha256']
assert not closure['live_related_processes']
assert len(report['cases']) == len(closure['rows']) == len(status['finished']) == 50
expected = {(1,v,n) for v in ('standard','random') for n in range(25)}
assert {(r['seed'],r['variant'],r['layout']) for r in report['cases']} == expected
assert len([p for p in (ROOT/'runs'/TAG).iterdir() if p.is_dir() and p.name.startswith('seed1-')]) == 50
for path, sha in freeze['source_sha256'].items():
    assert digest(path) == sha, path
checked = preflight(protocol)
head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
assert head == report['candidate_commit'] == '4878cd3871b160bad8548b71172b1d51c44e843a'
for path, sha in protocol['accepted_runtime_sha256'].items():
    original = subprocess.check_output(['git','show',f'{protocol["accepted_runtime_commit"]}:{path}'],cwd=ROOT)
    assert hashlib.sha256(original).hexdigest() == digest(ROOT/path) == sha, path
static = read(ROOT/protocol['verification']['static'])
assert static['passed'] and static['tests_run'] == 154
assert not static['failures'] and not static['errors'] and not static['skipped']
assert digest(static['log']) == static['log_sha256']
interfaces = read(ROOT/protocol['verification']['interfaces'])
unchanged = interfaces['unchanged_task_interfaces_and_prompts']
assert len(unchanged) == 10 and all(interfaces['before'][t] == interfaces['after'][t] for t in unchanged)
pack_tools = interfaces['after']['pack_objects_into_box']['names']
assert {'python_cell','hold_joints','inspect_transfer_reference','match_scene_reference','prepare_motion_transfer'} <= set(pack_tools)
assert 'execute_motion_transfer' not in pack_tools
reference = Path('/tmp/roborag-make-toast-pyrua-20261104')
pyrua_commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=reference,text=True).strip()
assert pyrua_commit == 'e8f01dca744421d70684adbbc1713fd4d92f8aca'

def independent_costs(audit):
    rows = audit['cases']
    result = {}
    for name in ('steps','wall_seconds','input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens'):
        values = [r.get(name) if name in ('steps','wall_seconds') else (r.get('usage') or {}).get(name) for r in rows]
        known = [v for v in values if v is not None]
        expected_cost = audit['all_attempt_costs'][name]
        assert len(known) == expected_cost['known_count']
        assert len(values)-len(known) == expected_cost['unknown_count']
        assert math.isclose(sum(known), expected_cost['known_sum'],rel_tol=1e-12,abs_tol=1e-6)
        result[name] = dict(known_count=len(known),unknown_count=len(values)-len(known),known_sum=sum(known))
    assert result['input_tokens']['known_sum']-result['cached_input_tokens']['known_sum'] == audit['all_attempt_costs']['uncached_input_tokens']['known_sum']
    assert result['input_tokens']['known_sum']+result['output_tokens']['known_sum'] == audit['all_attempt_costs']['total_tokens']['known_sum']
    return result

costs = independent_costs(report)
dev_path = ROOT/'results/pack-box-tools-v1-dev-20261107.json'
dev = read(dev_path)
assert dev['complete'] and dev['counts']['attempts_closed'] == 4
dev_costs = independent_costs(dev)
errors, aggregate_tools = [], Counter()
for row in report['cases']:
    directory = Path(row['directory'])
    run = read(directory/'run.json')
    ready = read(directory/'ready.json')
    assert run['args']['control_step_limit'] is None
    assert ready['native_step_limit'] == ready['step_limit'] == 1300
    assert ready['control_step_limit_override'] is None and ready['budget_mode'] == 'native'
    for path, sha in row['artifact_sha256'].items():
        assert digest(path) == sha, path
    calls = [json.loads(line) for line in (directory/'mcp-calls.jsonl').read_text().splitlines() if line.strip()]
    aggregate_tools.update(c['tool'] for c in calls)
    for call in calls:
        if call['tool'] == 'python_cell' and call['result'].get('error'):
            cell = call['result']
            errors.append(dict(case=directory.name,**{k:cell.get(k) for k in ('cell','error','step_before','step_after','action_steps')}))
rows = closure['rows']
stats = dict(completed_cells=sum(r['completed_cells'] for r in rows),
             cells_with_errors=sum(r['cells_with_errors'] for r in rows),
             moving_cells=sum(r['cells_with_motion'] for r in rows),
             cell_control_steps=sum(r['cell_motion_steps'] for r in rows),
             joint_hold_calls=sum(r['joint_hold_calls'] for r in rows),
             joint_hold_steps=sum(r['joint_hold_steps'] for r in rows),
             accepted_delta_rows=sum(r['native_guard_audit']['accepted_delta_rows'] for r in rows),
             rejected_ik_attempts=sum(r['native_guard_audit']['rejected_attempts'] for r in rows),
             cell_errors_with_control_steps=sum(bool(e['action_steps']) for e in errors),
             tool_counts=dict(aggregate_tools))
assert stats['cells_with_errors'] == len(errors)
native_processes = active_native_processes()
assert not any(TAG in ' '.join(p['argv']) for p in native_processes)
evidence_paths = [report_path,closure_path,freeze_path,Path(freeze['protocol']),dev_path,
                  ROOT/protocol['verification']['static'],ROOT/protocol['verification']['interfaces'],
                  ROOT/'results/pack-box-tools-bank-preflight-20261107.json',
                  ROOT/'results/pack-box-baseline-and-references-20261107.json']
final = dict(checked_at=datetime.now(timezone.utc).isoformat(),passed=True,experiment_complete=True,
             tag=TAG,candidate_commit=head,accepted_runtime_commit=protocol['accepted_runtime_commit'],
             closure=str(closure_path),closure_sha256=digest(closure_path),
             evidence_sha256={str(p):digest(p) for p in evidence_paths},
             frozen_sources_verified=len(freeze['source_sha256']),accepted_runtime_files_verified=len(protocol['accepted_runtime_sha256']),
             static_tests_verified=static['tests_run'],static_source_files_verified=len(static['source_sha256']),
             other_task_interfaces_and_prompts_verified=unchanged,pack_tool_names=pack_tools,
             preflight_reverification=checked,pyrua_reference_commit=pyrua_commit,
             counts=report['counts'],variants=report['variants'],native_budget=1300,control_step_limit_override=None,
             native_reports_verified=report['audit']['native_results_verified'],trajectories_verified=report['audit']['trajectories_checked'],
             registered_pid_count=len(closure['registered_pids']),registered_process_identities=closure['registered_process_identities'],
             policy_workspaces_checked=len(closure['policy_workspaces_checked']),live_related_processes=closure['live_related_processes'],
             other_native_processes_at_verification=native_processes,stats=stats,cell_errors=errors,
             formal_costs=report['all_attempt_costs'],batch_wall_seconds=report['batch_wall_seconds'],
             development_costs=dev['all_attempt_costs'],development_batch_wall_seconds=dev['batch_wall_seconds'],
             known_candidate_54_attempt_costs={k:dict(known_count=costs[k]['known_count']+dev_costs[k]['known_count'],unknown_count=costs[k]['unknown_count']+dev_costs[k]['unknown_count'],known_sum=costs[k]['known_sum']+dev_costs[k]['known_sum']) for k in costs},
             actual_billed_usd=None,cost_scope='These54 native attempts cover this candidate4-case modified2000 development and fresh50 native1300 evaluation only. Historical attempts, engineering/adaptation time and current-chat orchestration tokens are not included. Cached input is included in input; reasoning output is included in output. Cell/hold steps are subsets of control steps. No score merging across budgets.',
             interpretation=protocol['scope']['interpretation'],auditor_sha256=digest(__file__))
out.write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:final[k] for k in ('passed','experiment_complete','counts','stats','registered_pid_count','registered_process_identities','policy_workspaces_checked','preflight_reverification','other_native_processes_at_verification')},ensure_ascii=False))
