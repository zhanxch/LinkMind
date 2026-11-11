"""Rebuild public tables and verify byte-identical native evidence, offline.

--collect-native is a release-maintainer operation requiring the original local
report paths. Normal use reads only files shipped in this repository.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return json.loads((ROOT / relative).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(relative, value):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_csv(relative, rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    (ROOT / relative).write_text(stream.getvalue())


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]])


def counts(rows):
    return dict(success=sum(r['success'] is True for r in rows),
                failure=sum(r['success'] is False for r in rows),
                unscored=sum(r['success'] is None for r in rows))


def key(row):
    return row['seed'], row['variant'], row['layout']


def verify_native(row, namespace, phase, ordinal, collect):
    source = row.get('native_result')
    expected = row.get('native_sha256')
    success = row.get('success')
    result = dict(seed=row['seed'], variant=row['variant'], layout=row['layout'],
                  success=success, phase=phase, steps=row.get('steps'),
                  original_native_path=source, native_sha256=expected,
                  native_result=None, score=None)
    if not source:
        if success is not None or expected:
            raise ValueError('Scored attempt has no native evidence')
        return result
    if not isinstance(success, bool) or not expected:
        raise ValueError('Native evidence lacks recorded outcome/hash')
    relative = f'results/native/{namespace}/{phase}/{ordinal:03d}-seed{row["seed"]}-{row["variant"]}-l{row["layout"]}.json'
    target = ROOT / relative
    if collect:
        original = Path(source)
        if sha(original) != expected:
            raise ValueError(f'Original native report changed: {source}')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha(target) != expected:
            raise ValueError(f'Refusing to overwrite native evidence: {relative}')
        target.write_bytes(original.read_bytes())
    if sha(target) != expected:
        raise ValueError(f'Published native report changed: {relative}')
    native = json.loads(target.read_text())
    details = list(native['details'].values())
    if len(details) != 1 or details[0]['success'] is not success:
        raise ValueError(f'Native outcome mismatch: {relative}')
    recorded_score = row.get('native_score', row.get('score'))
    if recorded_score is not None and abs(native['score'] - recorded_score) > 1e-8:
        raise ValueError(f'Native score mismatch: {relative}')
    result.update(native_result=relative, score=native['score'])
    return result


def build_main_table():
    data = read('results/paper-main-table.json')
    methods = data['methods']
    rows, flat = [], []
    for row in [*data['rows'], dict(task='Mean (12 tasks)', cells=data['mean'])]:
        cells = row['cells']
        ranks = {metric: sorted({float(c[metric]) for c in cells.values()}, reverse=True)
                 for metric in ('score', 'success_rate')}
        formatted = []
        for method in methods:
            cell = cells[method]
            flat.append(dict(task=row['task'], method=method, **cell))
            pair = []
            for metric in ('score', 'success_rate'):
                text = cell[metric]
                rank = ranks[metric].index(float(text))
                pair.append(f'**{text}**' if rank == 0 else f'<ins>{text}</ins>' if rank == 1 else text)
            formatted.append(' / '.join(pair))
        rows.append([row['task'], *formatted])
    body = '''# Paper main table

Each cell is **Score / success rate (%)**, equally averaged over standard and randomized scenes. The mean row weights all 12 tasks equally. Bold marks the highest distinct value and underline the second-highest, separately for each metric; ties share ranks. Baseline precision and published mean values are retained.

This is a transcription of the saved paper main table, not a new evaluation of the integrated release. Unreported tasks follow the paper's **0.0 / 0.0 filling convention** and are included in its mean; these zeros do not establish measured failures. Local evaluations and public leaderboard submissions are not seed-matched.

'''
    body += table(['Task', *methods], rows) + '\n\n'
    body += '''The VLA/WAM columns are WALL-OSS 1.0-lite, VPP2, OpenWAM-alpha and Pi-05; the remaining columns are agent methods. Baselines are transcribed from the paper's recorded RoboDojo-Sim leaderboard / GPT-6-Astra evaluation sources, not refreshed from today's leaderboard.

## Evidence and scope

- The paper reports **Push-T 100.0 / 100.0**. The separately archived local toolkit run has **48 successes and 2 unscored scenes**; its confirmed success fraction is 96%, and success among its 48 scored attempts is 100%. These are different reporting scopes; this release does not claim a new 50/50 toolkit run.
- Arrange largest number (65.7 / 56.0) and Sort nesting dolls by size (82.0 / 82.0) are author-supplied paper results. Their native reports are not included in the local eight-task evidence package.
- Pour liquid into cup and Store laptop and headphones use the paper's unreported-task zero-fill convention.
- See [local native evidence](local-results.md) for per-task commits, budgets, failures, interruptions and supplements. That table preserves missing scores separately.
- The main-table source was the locally saved paper checkout `{commit}`. An authenticated Overleaf refresh was unavailable at release preparation; this does not certify the currently displayed online manuscript.

[Machine-readable table](../results/paper-main-table.json) · [CSV](../results/paper-main-table.csv). The JSON records source hashes. Only the table data and a newly written method explanation are published; manuscript text, TeX and PDFs are excluded.
'''.replace('{commit}', data['paper_checkout_commit'])
    (ROOT / 'docs/main-table.md').write_text(body)
    readme = ROOT / 'README.md'
    if '<!-- MAIN_TABLE_START -->' in readme.read_text():
        before, remainder = readme.read_text().split('<!-- MAIN_TABLE_START -->', 1)
        _, after = remainder.split('<!-- MAIN_TABLE_END -->', 1)
        readme.write_text(before + '<!-- MAIN_TABLE_START -->\n' +
                          table(['Task', *methods], rows) +
                          '\n<!-- MAIN_TABLE_END -->' + after)
    write_csv('results/paper-main-table.csv', flat)
    return table(['Task', *methods], rows)


def build_native_tables(collect=False):
    config = read('resources/published-experiments.json')
    attempts, scenarios, summaries, mdrows = [], [], [], []
    for task in config['tasks']:
        if sha(ROOT / task['protocol']) != task['protocol_sha256']:
            raise ValueError(f'Protocol drift: {task["task"]}')
        current, all_rows = {}, []
        for report in task['reports']:
            if sha(ROOT / report['path']) != report['sha256']:
                raise ValueError(f'Report drift: {report["path"]}')
            for i, row in enumerate(read(report['path'])[report['rows']]):
                normalized = verify_native(row, task['task'], report['phase'], i, collect)
                normalized.update(task=task['task'], candidate_commit=report['candidate_commit'],
                                  source_report=report['path'])
                k = key(normalized)
                if k in current and (report['phase'] != 'supplement' or current[k]['success'] is not None):
                    raise ValueError('Duplicate case or attempted replacement of scored result')
                current[k] = normalized
                all_rows.append(normalized)
        expected = {(1, v, l) for v in ('standard', 'random') for l in range(25)}
        if set(current) != expected:
            raise ValueError(f'Incomplete scenario coverage: {task["task"]}')
        rows = list(current.values())
        c = counts(rows)
        split = {v: counts([r for r in rows if r['variant'] == v]) for v in ('standard', 'random')}
        summary = dict(task=task['task'], **c, scenarios=len(rows), attempts=len(all_rows),
                       retained_unscored_attempts=counts(all_rows)['unscored'],
                       confirmed_success_pct=100*c['success']/50,
                       mean_native_score_scored=sum(r['score'] for r in rows if r['score'] is not None)/(50-c['unscored']),
                       native_steps=task['native_steps'], max_wall_seconds=task['max_wall_seconds'],
                       runtime_commit=task['runtime_commit'])
        summaries.append(summary)
        mdrows.append([task['task'], c['success'], c['failure'], c['unscored'],
                       f'{summary["confirmed_success_pct"]:.0f}%', len(all_rows),
                       summary['retained_unscored_attempts'], task['native_steps'],
                       f'`{task["runtime_commit"][:7]}`'])
        attempts.extend(all_rows)
        scenarios.extend(rows)
    dump('results/local-attempts.json', attempts)
    dump('results/local-scenarios.json', scenarios)
    dump('results/local-summary.json', summaries)
    write_csv('results/local-summary.csv', summaries)
    write_csv('results/local-attempts.csv', attempts)
    body = '''# Local native evidence

These results belong to the original per-task frozen candidates, **not a fresh run of the merged release**. All tasks use gpt-6-astra / xhigh, seed 1, standard/random layouts 0–24 (25 each). These are known evaluation/development layouts, not a new held-out generalization claim. Steps are native control limits; packing uses 1300, excluding earlier 2000-step development trials.

Confirmed success divides successes by 50 scenes. Unscored scenes are separate from native failures. Supplements fill only originally missing scores; every original interruption remains in the attempt ledger.

'''
    body += table(['Task','Success','Native failure','Unscored scenes','Confirmed / 50','All attempts','Retained unscored attempts','Step limit','Runtime source'], mdrows)
    body += '\n\n[Summary CSV](../results/local-summary.csv) · [All attempts CSV](../results/local-attempts.csv) · [Scenario ledger](../results/local-scenarios.json) · [Protocol/source manifest](../resources/published-experiments.json). Each scored attempt links to a byte-identical native report and its SHA-256; source reports remain unchanged. Unknown costs in source reports remain unknown.\n\n'
    body += 'The paper main table has its own documented reporting scope: see [main table](main-table.md). In particular the local Push-T toolkit run is 48 successful, 0 failed and 2 unscored, not 50/50.\n\n'
    body += '## Push-T simplification pilot\n\nFive profiles each ran one standard-l0 and one random-l0 attempt, seed 1, gpt-6-astra/xhigh, 600 steps / 5400 seconds. This is a ten-attempt development pilot, separate from the 50-scene toolkit run. All five profiles succeeded twice; this does not establish 50-scene non-inferiority or a causal component benefit.\n\n'
    pilot = read('results/push-t-simplification-pilot-20261111.json')
    pilot_rows = []
    for i, row in enumerate(pilot['cases']):
        phase = row.get('profile') or Path(row['directory']).name.split('-seed')[0]
        pilot_rows.append(dict(profile=phase, **verify_native(row, 'push-simplification', phase, i, collect)))
    dump('results/push-simplification-attempts.json', pilot_rows)
    body += table(['Profile','Success / attempts','Mean control steps','Mean wall seconds'],
                  [[name, f'{g["counts"]["success"]}/2', f'{g["costs"]["steps"]["known_mean"]:.1f}',
                    f'{g["costs"]["wall_seconds"]["known_mean"]:.1f}'] for name,g in pilot['groups'].items()])
    body += '\n\n[Native pilot ledger](../results/push-simplification-attempts.json) · [Original report](../results/push-t-simplification-pilot-20261111.json). Default runtime behavior remains the evaluated toolkit; select simplified profiles explicitly.\n\n'
    model = read('results/stack-bowls-model-comparison-20261109.json')
    model_rows = []
    for i, row in enumerate(model['attempts']):
        model_rows.append(dict(group=row['group'], **verify_native(row,'stack-models',row['group'],i,collect)))
    dump('results/stack-model-attempts.json', model_rows)
    body += '## Stack Bowls model comparison\n\nKnown seed-1 standard/random layouts 0–4, ten scenes per group, xhigh, 800 steps / 5400 seconds. Local implementations and model choices differ from the public leaderboard main table. The study has 60 scenes, 62 attempts, 58 native scores and 2 unresolved scenes; four unscored attempts are retained.\n\n'
    body += table(['Local method','Model','Success','Failure','Unscored scenes','Attempts'],
                  [[g['group']['method'],g['group']['model'],g['success'],g['failure'],g['unscored'],g['attempted']] for g in model['groups']])
    body += '\n\n[Original study report](../results/stack-bowls-model-comparison-20261109.json) · [Native attempt ledger](../results/stack-model-attempts.json). Paused/stopped FoldClothes, toast and experience-ablation queues are not treated as completed studies.\n'
    (ROOT / 'docs/local-results.md').write_text(body)
    return dict(main_scenarios=len(scenarios),main_attempts=len(attempts),
                main_native_reports=sum(r['native_result'] is not None for r in attempts),
                pilot_attempts=len(pilot_rows),model_attempts=len(model_rows),
                native_reports=sum(r['native_result'] is not None for r in attempts+pilot_rows+model_rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-native', action='store_true')
    args = parser.parse_args()
    build_main_table()
    report = build_native_tables(args.collect_native)
    dump('results/public-evidence-verification.json', dict(passed=True, **report))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
