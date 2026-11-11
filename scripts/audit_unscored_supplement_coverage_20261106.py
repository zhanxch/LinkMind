"""Seal missing-only scene coverage after native closure; never modify attempts."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('tag')
    parser.add_argument('closure', type=Path)
    parser.add_argument('launch', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root/'scripts'))
    from run_unscored_supplement import read, digest, key, verify_gate
    from audit_make_toast_results import counts, costs
    from roborag.rag_tasks import prompt_for
    import hashlib
    import json

    batch = root/'runs'/args.tag
    status = read(batch/'status.json')
    driver_path = root/'runs'/f'{args.tag}-driver.json'
    driver = read(driver_path)
    assert status['complete'] and not status['active'] and not status['pending']
    assert driver['phase'] == 'complete' and driver['batch_returncode'] == driver['audit_returncode'] == 0
    freeze_path = root/'runs'/f'{args.tag}-freeze.json'
    freeze = read(freeze_path)
    protocol = read(freeze['protocol'])
    report_path = root/'results'/f'{args.tag}.json'
    report, closure, launch = read(report_path), read(args.closure), read(args.launch)
    assert report['complete'] and report['audit']['passed'] and closure['complete']
    assert report['tag'] == closure['tag'] == launch['tag'] == args.tag
    assert report['candidate_commit'] == closure['candidate_commit'] == launch['registration_commit'] == freeze['candidate_commit']
    assert closure['report_sha256'] == digest(report_path)
    assert closure['freeze_sha256'] == launch['freeze_sha256'] == digest(freeze_path)
    assert closure['driver_sha256'] == digest(driver_path)
    assert closure['protocol_sha256'] == launch['protocol_sha256'] == digest(freeze['protocol'])
    assert not closure['live_related_processes']
    assert digest(protocol['authorization_evidence']['path']) == protocol['authorization_evidence']['sha256']
    parent, parent_freeze, parent_check = verify_gate(protocol['parent_batch'])
    other_checks = [verify_gate(gate)[2] for gate in protocol['required_closed_batches']]
    assert freeze['conditions'] == parent_freeze['conditions'] == protocol['conditions']
    assert freeze['prompt_sha256'] == parent_freeze['prompt_sha256'] == launch['prompt_sha256']
    assert protocol['accepted_runtime_commit'] == launch['accepted_runtime_commit']
    task = protocol['tasks'][0]['task']
    assert hashlib.sha256(prompt_for(root, task, 'delta').encode()).hexdigest() == freeze['prompt_sha256']
    for path, expected in freeze['source_sha256'].items():
        assert digest(path) == expected, ('supplement source drift', path)
    for base in [protocol['parent_batch']['candidate_commit'], protocol['accepted_runtime_commit']]:
        subprocess.run(['git', 'diff', '--exit-code', base, '--', 'src', 'prompts', 'tests'], cwd=root, check=True)
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', 'src', 'prompts', 'tests'], cwd=root, text=True).strip()

    declared = read(root/freeze['task']['cases_file'])
    missing = [row for row in parent['cases'] if row['success'] is None]
    expected = Counter(map(key, missing))
    assert expected == Counter(map(key, declared)) == Counter(map(key, report['cases'])) == Counter(map(key, status['finished'])) == Counter(map(key, closure['rows']))
    assert all(value == 1 for value in expected.values())
    assert len(declared) == protocol['planned_native_attempts'] == report['counts']['attempts_closed']
    assert report['counts'] == counts(report['cases']) == closure['counts']
    assert report['all_attempt_costs'] == costs(report['cases']) == closure['costs']
    assert parent['all_attempt_costs'] == costs(parent['cases'])
    for row in report['cases']:
        for path, expected_hash in row['artifact_sha256'].items():
            assert digest(path) == expected_hash, ('supplement evidence drift', path)
        native_paths = list(Path(row['directory']).rglob('_result.json'))
        if row['success'] is None:
            assert not native_paths and row['native_result'] is None
        else:
            assert len(native_paths) == 1 and digest(native_paths[0]) == row['native_sha256']

    # Independently recheck current processes; old PID numbers alone are insufficient.
    identities = set()
    for line in (batch/'resources.jsonl').read_text().splitlines():
        sample = json.loads(line)
        for group in sample.get('owned_processes', {}).values():
            identities.update((row['pid'], row['started_epoch']) for row in group)
    boot = int(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime ')))
    hz = os.sysconf('SC_CLK_TCK')
    live = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            command = (proc/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            stat = (proc/'stat').read_text().rsplit(')', 1)[1].split()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        if not command.strip() or stat[0] == 'Z':
            continue
        pid, ticks = int(proc.name), int(stat[19])
        birth = boot + ticks/hz
        known = any(pid == p and abs(birth-t) < .1 for p,t in identities)
        driver_or_batch = any(pid == launch[name]['pid'] and ticks == launch[name]['start_ticks'] for name in ['driver', 'batch'])
        related = str(batch) in command or any(path in command for path in closure['policy_workspaces_checked'])
        if known or driver_or_batch or related:
            live.append(dict(pid=pid, start_ticks=ticks, command=command))
    assert not live, live

    # Previously passing static results remain evidence only if the tested sources match.
    static_name = ('hang-mugs-guard-v2-static-tests-20261105.json' if task == 'hang_mugs'
                   else 'sweep-blocks-tools-v1-static-tests-20261106.json')
    static_path = root/'results'/static_name
    static = read(static_path)
    expected_static_hash = ('c3766f5d3fac81b1a1ccb2edb01b7ce7d93054e14f5fe4717968f4d3d8b0e17b'
                            if task == 'hang_mugs' else
                            '5bc8b89edc9d27fd964ff31220cdae9f77a651288733c4c42efa7dfdc1ca462d')
    assert digest(static_path) == expected_static_hash
    assert static['passed']
    for path, expected_hash in static['source_sha256'].items():
        assert digest(path) == expected_hash, ('tested source changed', path)
    assert digest(static['log']) == static['log_sha256']

    supplemental = {key(row): row for row in report['cases']}
    chosen, scene_rows = [], []
    for original in parent['cases']:
        filled = original['success'] is None
        selected = supplemental[key(original)] if filled else original
        chosen.append(selected)
        scene_rows.append(dict(seed=original['seed'], variant=original['variant'], layout=original['layout'],
                               selected_batch=args.tag if filled else parent['tag'],
                               filled_original_missing_score=filled,
                               original_success=original['success'], success=selected['success'],
                               native_score=selected['native_score'], native_result=selected['native_result'],
                               native_sha256=selected['native_sha256']))
    assert len(chosen) == len(set(map(key, chosen))) == 50
    all_rows = parent['cases'] + report['cases']
    all_counts = counts(all_rows)
    assert all_counts['unscored'] == parent['counts']['unscored'] + report['counts']['unscored']
    closed_rows = closure['rows']
    tool_fields = ['completed_cells', 'cells_with_errors', 'truncated_or_stopped_cells',
                   'measurements_verified_zero_steps', 'measurement_errors']
    tool_totals = {name: dict(known_sum=(sum(row[name] for row in closed_rows if name in row)
                                        if any(name in row for row in closed_rows) else None),
                              available_attempts=sum(name in row for row in closed_rows)) for name in tool_fields}
    guard_rows = [row['native_guard_audit'] for row in closed_rows if 'native_guard_audit' in row]
    interruptions = []
    for row in report['cases']:
        if row['success'] is None or row['failure'] or not row['usage']:
            hashes = {}
            for name in ['agent-events.jsonl', 'agent.log', 'runner.log', 'agent-exit.json', 'exit.json']:
                path = Path(row['directory'])/name
                if path.exists():
                    hashes[str(path)] = digest(path)
            interruptions.append(dict(seed=row['seed'], variant=row['variant'], layout=row['layout'],
                                      success=row['success'], failure=row['failure'], usage=row['usage'],
                                      terminal_artifact_sha256=hashes))
    result = dict(schema='roborag.missing-score-supplement-coverage.v1', checked_at=datetime.now(timezone.utc).isoformat(),
                  passed=True, complete=True, task=task, tag=args.tag, root=str(root),
                  candidate_commit=freeze['candidate_commit'], accepted_runtime_commit=protocol['accepted_runtime_commit'],
                  audit_script=str(Path(__file__).resolve()), audit_script_sha256=digest(__file__),
                  native_report=str(report_path), native_report_sha256=digest(report_path),
                  closure=str(args.closure.resolve()), closure_sha256=digest(args.closure),
                  launch_verification=str(args.launch.resolve()), launch_verification_sha256=digest(args.launch),
                  protocol=freeze['protocol'], protocol_sha256=digest(freeze['protocol']),
                  freeze_sha256=digest(freeze_path), prompt_sha256=freeze['prompt_sha256'],
                  frozen_sources_verified=len(freeze['source_sha256']), parent_preserved=parent_check,
                  other_original_batches_preserved=other_checks, runtime_prompts_tests_unchanged=True,
                  static_evidence=dict(report=str(static_path), sha256=digest(static_path), tests_run=static['tests_run'],
                                       sources_rechecked=len(static['source_sha256']), rerun=False),
                  first_pass=dict(report=protocol['parent_batch']['report'], sha256=protocol['parent_batch']['report_sha256'],
                                  counts=parent['counts'], variants=parent['variants'], costs=parent['all_attempt_costs'],
                                  batch_wall_seconds=parent['batch_wall_seconds']),
                  supplement=dict(counts=report['counts'], variants=report['variants'], costs=report['all_attempt_costs'],
                                  batch_wall_seconds=report['batch_wall_seconds']),
                  missing_only_50_scene_coverage=dict(counts=counts(chosen),
                        variants={variant:counts([row for row in chosen if row['variant'] == variant]) for variant in ['standard','random']},
                        rows=scene_rows, rule='Use the single supplement only where original native score was missing; never replace scored failures.'),
                  all_attempts=dict(counts=all_counts, costs=costs(all_rows),
                                    sum_batch_wall_seconds=parent['batch_wall_seconds']+report['batch_wall_seconds']),
                  supplement_tools=tool_totals,
                  native_guard_scored_attempts_only=dict(attempts=len(guard_rows),
                        accepted_delta_rows=sum(row['accepted_delta_rows'] for row in guard_rows),
                        rejected_attempts=sum(row['rejected_attempts'] for row in guard_rows),
                        excluded_unscored_attempts=report['counts']['unscored']),
                  interruptions=interruptions, live_related_processes=live, actual_billed_usd=None,
                  cost_scope='All original full50 and supplemental attempts, including original unscored costs. Development, implementation, static tests and operator analysis remain separate. Cached input is part of input and reasoning output is part of output; do not add twice. Unknown usage and billing remain unknown.',
                  interpretation=protocol['scope']['interpretation'])
    assert not args.output.exists(), 'Never overwrite a sealed audit'
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, first_pass=parent['counts'], supplement=report['counts'],
                         coverage=result['missing_only_50_scene_coverage']['counts'], all_attempts=all_counts,
                         frozen_sources_verified=len(freeze['source_sha256']))))


if __name__ == '__main__':
    main()
