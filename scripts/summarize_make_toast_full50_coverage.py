"""Fill only originally unscored scene outcomes, retaining all 53 attempts."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def key(row):
    return row['seed'], row['variant'], row['layout']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('closure', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    closure = read(args.closure)
    assert closure['complete'] and not closure['live_related_processes']
    supplement_path = Path(closure['report'])
    assert digest(supplement_path) == closure['report_sha256']
    supplement = read(supplement_path)
    protocol_path = Path(closure['protocol'])
    assert digest(protocol_path) == closure['protocol_sha256']
    protocol = read(protocol_path)
    parent = protocol['parent_batch']
    original_path = Path(parent['report'])
    assert digest(original_path) == parent['report_sha256']
    original = read(original_path)
    assert original['complete'] and supplement['complete']
    assert original['audit']['passed'] and supplement['audit']['passed']
    assert len(original['cases']) == 50 and len(supplement['cases']) == 3
    original_cases = {key(r): r for r in original['cases']}
    supplement_cases = {key(r): r for r in supplement['cases']}
    assert len(original_cases) == 50 and len(supplement_cases) == 3
    assert set(supplement_cases) == {k for k, r in original_cases.items() if r['success'] is None}
    freezes = [read(parent['freeze']), read(root / 'runs' / (supplement['tag'] + '-freeze.json'))]
    assert freezes[0]['conditions'] == freezes[1]['conditions']
    assert freezes[0]['prompt_sha256'] == freezes[1]['prompt_sha256']
    runtime = {p: h for p, h in freezes[0]['source_sha256'].items()
               if Path(p).is_relative_to(root / 'src') or Path(p).is_relative_to(root / 'prompts')}
    assert runtime
    for path, expected in runtime.items():
        assert freezes[1]['source_sha256'][path] == expected == digest(path), path
    spec = importlib.util.spec_from_file_location('toast_accounting', root / 'scripts/audit_make_toast_results.py')
    accounting = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(accounting)
    coverage = [supplement_cases.get(k, r) for k, r in original_cases.items()]
    all_attempts = original['cases'] + supplement['cases']
    variants = {}
    for variant in ('standard', 'random'):
        rows = [r for r in coverage if r['variant'] == variant]
        scored = [r['native_score'] for r in rows if r['success'] is not None]
        variants[variant] = dict(**accounting.counts(rows),
                                 mean_native_score_scored=statistics.mean(scored) if scored else None)
    report = dict(
        checked_at=datetime.now(timezone.utc).isoformat(),
        original_report=str(original_path), original_report_sha256=digest(original_path),
        supplement_report=str(supplement_path), supplement_report_sha256=digest(supplement_path),
        closure=str(args.closure.resolve()), closure_sha256=digest(args.closure),
        original_commit=original['candidate_commit'], supplement_commit=supplement['candidate_commit'],
        identical_runtime_sources_verified=len(runtime), prompt_sha256=freezes[0]['prompt_sha256'],
        first_pass_counts=original['counts'], supplement_counts=supplement['counts'],
        all_53_attempt_counts=accounting.counts(all_attempts),
        all_53_attempt_costs=accounting.costs(all_attempts),
        fifty_scene_coverage_counts=accounting.counts(coverage),
        fifty_scene_coverage_variants=variants,
        fifty_scene_coverage=[dict(seed=r['seed'], variant=r['variant'], layout=r['layout'],
                                   success=r['success'], native_score=r['native_score'], steps=r['steps'],
                                   source_attempt=r['directory'], native_result=r['native_result'],
                                   native_sha256=r['native_sha256'],
                                   supplemental=key(r) in supplement_cases) for r in coverage],
        batch_wall_seconds=dict(first_pass=original['batch_wall_seconds'],
                                supplement=supplement['batch_wall_seconds']),
        actual_billed_usd=None,
        interpretation='50 unique registered scenes, filling only 3 originally unscored outcomes from a separately registered unchanged-runtime supplement. This is 53 attempts across two batches, not a new single-pass 50-case run. All original failures, interruptions and known/unknown costs remain preserved; no heldout or component-causality claim.')
    assert not args.output.exists(), 'Do not overwrite coverage evidence'
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('first_pass_counts', 'supplement_counts',
                                             'all_53_attempt_counts', 'fifty_scene_coverage_counts')}))


if __name__ == '__main__':
    main()
