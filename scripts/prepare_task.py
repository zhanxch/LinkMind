"""Verify and install a frozen task bank, without annotation or model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def child(root, relative):
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes root: {relative}')
    return path


def prepare(task, *, root=ROOT, data=None, metadata_only=False, verify_only=False):
    manifest = json.loads((root / 'resources/task-bundles.json').read_text())
    record = manifest['tasks'][task]
    bundle = child(root, record['bundle'])
    data = data or root / 'data'
    files = [(child(bundle, name), child(root, record['install']) / name, sha)
             for name, sha in record['metadata_sha256'].items()]
    if task == 'push_T':
        fixed = manifest['push_fixed_reference']
        files.append((child(root, fixed['path']), child(root, fixed['install']), fixed['sha256']))
    # Validate everything before writing. Existing different banks are never replaced.
    for source, target, sha in files:
        if digest(source) != sha:
            raise ValueError(f'Bundled metadata mismatch: {source}')
        if target.exists() and digest(target) != sha:
            raise ValueError(f'Refusing to replace different installed metadata: {target}')
    if not metadata_only:
        for row in record['train']:
            path = child(data, row['path'])
            if path.stat().st_size != row['bytes'] or digest(path) != row['sha256']:
                raise ValueError(f'TRAIN mismatch: {path}')
    if not verify_only:
        for source, target, _ in files:
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    return dict(task=task, metadata_files=len(files), train_verified=not metadata_only,
                train_files=len(record['train']), installed=not verify_only,
                bank=record['install'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True)
    parser.add_argument('--data', type=Path, default=ROOT / 'data')
    parser.add_argument('--metadata-only', action='store_true', help='For offline tests; does not verify TRAIN data')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'resources/task-bundles.json').read_text())
    tasks = list(manifest['tasks']) if args.task == 'all' else [args.task]
    for task in tasks:
        print(json.dumps(prepare(task, data=args.data, metadata_only=args.metadata_only,
                                 verify_only=args.verify_only)))


if __name__ == '__main__':
    main()
