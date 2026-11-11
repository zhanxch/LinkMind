import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_fold_reproduction import child, prepare


class FoldReproductionTests(unittest.TestCase):
    def test_portable_install_checks_sources_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle, data, output = [root / name for name in ("bundle", "data", "output")]
            (bundle / "graphs").mkdir(parents=True)
            data.mkdir()
            graphs = []
            for i in range(3):
                source = data / f"demo-{i}"
                source.write_bytes(f"TRAIN {i}".encode())
                graphs.append(dict(id=f"fold_clothes-{i:04}", task="fold_clothes"))
                (bundle / "graphs" / f"fold_clothes-{i:04}.json").write_text(json.dumps(
                    dict(source=dict(path=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest()))))
            (bundle / "execution-index.json").write_text(json.dumps(dict(graphs=graphs)))
            hashes = {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in bundle.rglob("*.json")}
            (bundle / "source-inventory.json").write_text(json.dumps(dict(
                metadata_sha256=hashes, counts=dict(demonstrations=3))))
            result = prepare(bundle, data, output)
            self.assertEqual(len(result["verified_train_sources"]), 3)
            for relative in hashes:
                self.assertEqual((bundle / relative).read_bytes(), (output / relative).read_bytes())
            with self.assertRaises(FileExistsError):
                prepare(bundle, data, output)
            (data / "demo-0").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "TRAIN hash mismatch"):
                prepare(bundle, data)
            (bundle / "execution-index.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "metadata hash mismatch"):
                prepare(bundle, data)

    def test_paths_stay_inside_bundle_and_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            for relative in ("../outside", "/tmp/outside"):
                with self.assertRaises(ValueError):
                    child(Path(tmp), relative)
