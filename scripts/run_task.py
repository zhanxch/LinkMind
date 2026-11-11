"""Unified single-episode entry point using each task's published frozen bank."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    manifest = json.loads((ROOT / 'resources/task-bundles.json').read_text())
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--task', choices=manifest['tasks'], default='stack_blocks')
    parser.add_argument('--bank')
    args, _ = parser.parse_known_args()
    if args.bank is None:
        bank = ROOT / manifest['tasks'][args.task]['install']
        if not (bank / 'execution-index.json').is_file() and not any(x in sys.argv for x in ('-h', '--help')):
            parser.error(f'Missing frozen bank. Run: python scripts/prepare_task.py --task {args.task}')
        sys.argv.extend(['--bank', str(bank)])
    from roborag.rag_runner import main as run
    run()


if __name__ == '__main__':
    main()
