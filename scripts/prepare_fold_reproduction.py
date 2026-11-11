"""Install the published frozen Foldclothes bank after verifying TRAIN sources.

Only copies metadata. Download the three public HDF5 demonstrations separately
with fetch_demonstrations.py. No model calls or simulator processes are started.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def child(root, relative):
    root = root.resolve()
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root):
        raise ValueError(f"Path escapes its data directory: {relative}")
    return path


def prepare(bundle, data, output=None):
    inventory = json.loads((bundle / "source-inventory.json").read_text())
    files = inventory["metadata_sha256"]
    for relative, expected in files.items():
        path = child(bundle, relative)
        if digest(path) != expected:
            raise ValueError(f"Frozen metadata hash mismatch: {relative}")
    index = json.loads((bundle / "execution-index.json").read_text())
    graphs = [g for g in index["graphs"] if g["task"] == "fold_clothes"]
    if len(graphs) != 3:
        raise ValueError("Expected all three original Foldclothes demonstrations")
    verified = {}
    for record in graphs:
        graph = json.loads(child(bundle, f"graphs/{record['id']}.json").read_text())
        source = graph["source"]
        path = child(data, source["path"])
        if digest(path) != source["sha256"]:
            raise ValueError(f"TRAIN hash mismatch: {path}")
        verified[source["path"]] = source["sha256"]
    if output is not None:
        # Never replace a bank used by an existing experiment.
        output.mkdir(parents=True, exist_ok=False)
        for relative in [*files, "source-inventory.json"]:
            target = child(output, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(child(bundle, relative), target)
    return dict(metadata_files=len(files), counts=inventory["counts"],
                verified_train_sources=verified,
                output=str(output) if output is not None else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=ROOT / "resources/fold-v3-full")
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/fold-v3-full")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    report = prepare(args.bundle.resolve(), args.data.resolve(),
                     None if args.verify_only else args.output.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
