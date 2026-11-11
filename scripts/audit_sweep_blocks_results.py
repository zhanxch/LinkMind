"""Native sweep report using the shared provenance and missing-counter checks."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import statistics

from audit_make_toast_results import audit_task, digest, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    protocol = read_json(args.protocol)
    freeze = read_json(ROOT/'runs'/f'{args.tag}-freeze.json')
    assert Path(freeze['protocol']).resolve() == args.protocol.resolve()
    assert freeze['task']['task'] == 'sweep_blocks'
    report = audit_task(args.tag, freeze['candidate_commit'], protocol, digest(args.protocol))
    report.update(schema='roborag.sweep-blocks-results-audit.v1',
                  generated_at=datetime.now(timezone.utc).isoformat(), protocol_sha256=digest(args.protocol),
                  base_commit=protocol['base_commit'], interpretation=protocol['scope']['interpretation'],
                  actual_billed_usd=None, auditor=dict(path=str(Path(__file__).resolve()),sha256=digest(__file__)))
    for variant, values in report['variants'].items():
        scores = [r['native_score'] for r in report['cases'] if r['variant'] == variant and r['native_score'] is not None]
        values['mean_native_score_scored'] = statistics.mean(scores) if scores else None
    scores = [r['native_score'] for r in report['cases'] if r['native_score'] is not None]
    report['mean_native_score_scored'] = statistics.mean(scores) if scores else None
    assert not args.output.exists(), 'Preserve existing evidence'
    write_json(args.output, report)
    print(json.dumps({k:report[k] for k in ['complete','candidate_commit','counts','audit']}))
    if not report['audit']['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
