"""Seal full50 provenance only after the existing native/feature audits close.

This preparation file lives outside the frozen worktree and does not run policy.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

ROOT = Path('/home/zxc/文档/ChatGPT/RoboRAG/work/sweep-blocks-tools')
TAG = 'sweep-blocks-tools-v1-full50-20261106'
REGISTRATION = 'd5cbac71d47b1265883cd59c9db2a99ba645b164'
ACCEPTED = 'ca604e59ea87b280b14757c23134bf62701a9cbd'

def read(path):
    return json.loads(Path(path).read_text())

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def verify(mapping):
    for path, expected in mapping.items():
        assert sha(path) == expected, path
    return len(mapping)

def key(row):
    return row['seed'], row['variant'], row['layout']

batch = ROOT/'runs'/TAG
status = read(batch/'status.json')
assert status['complete'] and not status['active'] and not status['pending'], 'Native batch is still active; no report written'
driver_path = ROOT/'runs'/f'{TAG}-driver.json'
driver = read(driver_path)
assert driver['phase'] == 'complete'
freeze_path = ROOT/'runs'/f'{TAG}-freeze.json'
freeze = read(freeze_path)
protocol = read(freeze['protocol'])
assert freeze['candidate_commit'] == REGISTRATION
assert protocol['accepted_runtime_commit'] == ACCEPTED
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == REGISTRATION
assert not subprocess.check_output(['git', 'diff', '--name-only', 'HEAD', '--', 'src', 'prompts', 'tests'], cwd=ROOT, text=True).strip()
native_path = ROOT/'results'/f'{TAG}.json'
native = read(native_path)
closure_path = ROOT/'results/sweep-blocks-tools-v1-full50-closure-20261106.json'
closure = read(closure_path)
assert native['complete'] and native['audit']['passed'] and closure['complete']
assert native['candidate_commit'] == closure['candidate_commit'] == REGISTRATION
assert native['counts'] == closure['counts'] and native['counts']['attempts_closed'] == 50
assert sha(native_path) == closure['report_sha256'] and sha(freeze_path) == closure['freeze_sha256']
assert sha(driver_path) == closure['driver_sha256'] and not closure['live_related_processes']
expected_cases = read(ROOT/freeze['task']['cases_file'])
assert len(expected_cases) == len(set(map(key, expected_cases))) == 50
assert set(map(key, expected_cases)) == set(map(key, native['cases'])) == set(map(key, closure['rows']))
for pid, expected_ticks in [(1458551, 193696319), (1458555, 193696546)]:
    proc = Path('/proc')/str(pid)
    try:
        ticks = int((proc/'stat').read_text().rsplit(')', 1)[1].split()[19])
        command = (proc/'cmdline').read_bytes()
    except (FileNotFoundError, ProcessLookupError):
        continue
    assert ticks != expected_ticks or not command, ('Original driver or scheduler is still live', pid)
live = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        cmd = (proc/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    if str(batch) in cmd or any(path in cmd for path in closure['policy_workspaces_checked']):
        live.append({'pid': int(proc.name), 'command': cmd})
assert not live, live
frozen_count = verify(freeze['source_sha256'])
preflight_path = ROOT/'results/sweep-blocks-full50-preflight-20261106.json'
preflight = read(preflight_path)
assert preflight['passed'] and preflight['protocol_sha256'] == sha(freeze['protocol'])
runtime_files = preflight['runtime_files_byte_identical']
assert len(runtime_files) == 61
for path in runtime_files:
    assert (ROOT/path).read_bytes() == subprocess.check_output(['git', 'show', f'{ACCEPTED}:{path}'], cwd=ROOT), path
static_path = ROOT/protocol['verification']['static']
static = read(static_path)
assert static['passed'] and static['tests_run'] == 133 and sha(static_path) == protocol['verification']['static_sha256']
static_count = verify(static['source_sha256'])
assert sha(static['log']) == static['log_sha256']
interface_path = ROOT/protocol['verification']['interfaces']
interfaces = read(interface_path)
assert interfaces['passed'] and sha(interface_path) == protocol['verification']['interfaces_sha256']
base = read(ROOT/'results/sweep-blocks-baseline-and-references-20261106.json')
assert sha(base['sealed_audit']) == base['sealed_audit_sha256']
old = read(base['sealed_audit'])
old_artifacts = sum(verify(row['artifact_sha256']) for row in old['cases'])
for row in old['cases']:
    if row['native_result']:
        assert sha(row['native_result']) == row['native_sha256']
assert sha(Path(base['baseline_root'])/'runs'/f"{old['tag']}-freeze.json") == base['freeze_sha256']
reference = base['reference']
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=reference['root'], text=True).strip() == reference['commit']
verify({str(Path(reference['root'])/path): digest for path, digest in reference['files'].items()})
previous = []
for gate in protocol['required_closed_batches']:
    assert sha(gate['closure']) == gate['closure_sha256']
    prior = read(gate['closure'])
    prior_freeze = read(gate['freeze'])
    assert prior['complete'] and not prior['live_related_processes']
    assert prior['candidate_commit'] == gate['candidate_commit'] and prior['counts']['attempts_closed'] == gate['attempts_closed']
    sources = verify(prior_freeze['source_sha256'])
    reports = 0
    for row in prior['rows']:
        if row['native_result']:
            assert sha(row['native_result']) == row['native_sha256']
            reports += 1
    previous.append(dict(closure=gate['closure'], closure_sha256=gate['closure_sha256'], frozen_sources_preserved=sources, native_reports_preserved=reports, counts=prior['counts']))
dev = protocol['development_evidence']
for name in ['native_report', 'closure', 'final_provenance', 'feature_trace']:
    assert sha(ROOT/dev[name]) == dev[name+'_sha256']
development = read(ROOT/dev['native_report'])
assert development['counts'] == dev['counts']
feature_path = ROOT/'results/sweep-blocks-tools-v1-full50-feature-trace-20261106.json'
feature = read(feature_path)
assert feature['native_audit_sha256'] == sha(native_path) and feature['freeze_sha256'] == sha(freeze_path)
assert feature['auditor_sha256'] == sha(ROOT/'scripts/audit_sweep_feature_calls.py')
assert feature['helper_source_sha256'] == sha(ROOT/'src/roborag/mcp/sweep_worker.py')
assert feature['candidate_commit'] == REGISTRATION
rows = []
interruptions = []
closed = {key(row): row for row in closure['rows']}
for row in native['cases']:
    directory = Path(row['directory'])
    verify(row['artifact_sha256'])
    if row['native_result']:
        assert sha(row['native_result']) == row['native_sha256']
    trace = directory/'mcp-calls.jsonl'
    calls = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()] if trace.exists() else []
    cells = [call['result'] for call in calls if call['tool'] == 'python_cell']
    details = closed[key(row)]
    guard = details.get('native_guard_audit')
    rows.append(dict(seed=row['seed'], variant=row['variant'], layout=row['layout'], success=row['success'], native_score=row['native_score'], steps=row['steps'], steps_complete=row['steps_complete'], native_result=row['native_result'], native_sha256=row['native_sha256'], tool_trace_available=trace.exists(), completed_cells=len(cells) if trace.exists() else None, cells_with_errors=sum(bool(cell.get('error')) for cell in cells) if trace.exists() else None, moving_cells=sum(cell['action_steps'] > 0 for cell in cells) if trace.exists() else None, cell_motion_steps=sum(cell['action_steps'] for cell in cells) if trace.exists() else None, joint_hold_calls=details['joint_hold_calls'] if trace.exists() else None, guard_accepted_rows=guard['accepted_delta_rows'] if guard else None, guard_rejections=guard['rejected_attempts'] if guard else None))
    exit_path = directory/'exit.json'
    exit_data = read(exit_path) if exit_path.exists() else {}
    if exit_data.get('error'):
        events_path = directory/'agent-events.jsonl'
        terminal_events, malformed_lines = [], 0
        if events_path.exists():
            for line in events_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    malformed_lines += 1
                    continue
                if event.get('type') in ('error', 'turn.failed', 'turn.completed'):
                    terminal_events.append(event)
        evidence_paths = [directory/name for name in ['exit.json', 'agent-exit.json', 'agent-events.jsonl', 'agent-stderr.log'] if (directory/name).exists()]
        interruptions.append(dict(seed=row['seed'], variant=row['variant'], layout=row['layout'], runner_error=exit_data['error'], runner_detail=exit_data.get('detail'), wall_seconds=row['wall_seconds'], success=row['success'], native_score=row['native_score'], steps=row['steps'], steps_complete=row['steps_complete'], terminal_usage_available=row['usage'] is not None, recent_terminal_events=terminal_events[-8:], malformed_event_lines=malformed_lines, artifact_sha256={str(path): sha(path) for path in evidence_paths}))
totals = {}
for name in ['completed_cells', 'cells_with_errors', 'moving_cells', 'cell_motion_steps', 'joint_hold_calls', 'guard_accepted_rows', 'guard_rejections']:
    values = [row[name] for row in rows if row[name] is not None]
    totals[name] = dict(known_sum=sum(values), available_attempts=len(values), unavailable_attempts=len(rows)-len(values))
assert feature['counts']['positive_steps'] <= totals['cell_motion_steps']['known_sum']
result = dict(audit_script=str(Path(__file__).resolve()), audit_script_sha256=sha(__file__), checked_at=datetime.now(timezone.utc).isoformat(), passed=True, complete=True, tag=TAG, candidate_commit=REGISTRATION, accepted_runtime_commit=ACCEPTED, native_report=str(native_path), native_report_sha256=sha(native_path), closure=str(closure_path), closure_sha256=sha(closure_path), frozen_sources_verified=frozen_count, runtime_and_prompt_files_equal_to_accepted_commit=runtime_files, static_tests=dict(tests_run=133, report=str(static_path), sha256=sha(static_path), tested_sources_unchanged=static_count, rerun=False), unchanged_task_interfaces_and_prompts=interfaces['unchanged_task_interfaces_and_prompts'], interface_report_sha256=sha(interface_path), prior_batches_preserved=previous, baseline=dict(commit=base['baseline_commit'], sealed_report=base['sealed_audit'], sha256=base['sealed_audit_sha256'], attempts_preserved=len(old['cases']), artifacts_preserved=old_artifacts, native_reports_preserved=sum(bool(row['native_result']) for row in old['cases']), unstarted_cases=44), reference=reference, rows=rows, counts=native['counts'], variants=native['variants'], totals=totals, feature_trace=str(feature_path), feature_trace_sha256=sha(feature_path), feature_counts=feature['counts'], costs=native['all_attempt_costs'], batch_wall_seconds=native['batch_wall_seconds'], separate_development=dict(report=dev['native_report'], sha256=dev['native_report_sha256'], counts=development['counts'], costs=development['all_attempt_costs'], batch_wall_seconds=development['batch_wall_seconds']), actual_billed_usd=None, live_related_processes=live, cost_scope='Full50 native attempts only. Four development attempts and their costs are separate; implementation/static/operator analysis costs are excluded. Reasoning tokens are included in output, not added twice. Unknown usage and billing remain unknown.', interpretation='All 50 registered seed1 scenes are fresh attempts, including the four development scenes. Historical sweep is 4 scored failures plus 2 unscored attempts and 44 unstarted, not a 0/50 baseline. Preserve failures and unscored attempts; no best-of merge. Observed helper counts are conservative and do not prove physical grasp or causal improvement. This is not heldout or cross-seed evidence.')
result['closed_attempt_interruptions'] = interruptions
result['interruption_interpretation'] = 'Native scoring and policy termination are separate. Preserve any valid native score obtained before policy timeout; a missing native report remains unscored. Missing terminal token usage is unknown in either case. Event/log hashes preserve service errors separately from recoverable cell execution errors.'
output = ROOT/'results/sweep-blocks-tools-v1-full50-final-provenance-20261106.json'
with output.open('x') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({name: result[name] for name in ['passed', 'counts', 'frozen_sources_verified', 'totals', 'feature_counts']}, ensure_ascii=False))
