# Install and run

The Python import namespace remains `roborag` to preserve compatibility. The unified public entry point is `scripts/run_task.py`. The release registers 12 tasks and bundles their frozen experience metadata; original TRAIN videos/HDF5, simulator assets and third-party runtimes are installed separately.

## Dependencies

Use Linux, Python 3.11 for the policy process, an Isaac Sim 5.1 environment and a GPU suitable for RoboDojo. Install the simulation and policy environments according to the pinned upstream projects:

```bash
git clone https://github.com/zhanxch/LinkMind.git
cd LinkMind
mkdir -p vendor
git clone https://github.com/Mosi-AI/RoboICL.git vendor/RoboICL
git -C vendor/RoboICL checkout 07d6e1c5387710e2de9240724b0015bbf0c95c6e
git -C vendor/RoboICL submodule update --init --recursive
git clone https://github.com/HexaFuture/HexaShell.git vendor/HexaShell
git -C vendor/HexaShell checkout d1a2a24dc4c528a652b359fd689398530ef941d8
cp local.runtime.example.json local.runtime.json
```

RoboDojo is pinned through RoboICL's submodule at `00ef04cd245bfa76e6f1e0bd8383c82f7964f942`. Fill `local.runtime.json` with your absolute interpreter, upstream, asset and simulator-library paths. Link `data/Assets` to the installed assets. Do not commit machine configuration or authentication files.

The policy environment needs the upstream dependencies plus NumPy, SciPy, h5py, Pillow, psutil and jsonschema. Install MCP separately from the simulator environment:

```bash
python -m pip install numpy scipy h5py Pillow psutil jsonschema
python -m pip install --target .runtime/mcp -r experiments/rag-mcp-requirements.txt
export PYTHONPATH=src:.runtime/mcp
export COMPARE_CODEX_BIN=/absolute/path/to/codex
```

The isolated agent/cell worker runs **`/usr/bin/python3`**, separately from the policy interpreter. Install its numerical/image libraries with that interpreter's ABI (Python 3.10 in the evaluated environment):

```bash
/usr/bin/python3 -m venv .venv-worker
.venv-worker/bin/python -m pip install --target data/hexashell-agent-python \
  -r experiments/worker-requirements.txt
PYTHONPATH=data/hexashell-agent-python /usr/bin/python3 -c 'import numpy, scipy, PIL, cv2, transforms3d'
```

Use the system's Python venv package if `venv` is unavailable. The worker mounts only this package directory and its worker script; missing packages cause the isolated worker to exit. Do not point it at Python 3.11 binary packages when `/usr/bin/python3` is 3.10.

The runtime requires `bwrap`, `curl`, `nvidia-smi` and an authenticated compatible policy CLI. Historical evaluations used CLI `0.155.0-alpha.16.3`; CLI flags and model availability are version-specific. The commands preserve that evaluated interface rather than guaranteeing compatibility with arbitrary newer CLI releases. Record any model or transport changes as a new configuration. No credentials are distributed.

## Frozen demonstration banks

[task-bundles.json](../resources/task-bundles.json) lists all 12 tasks, pinned dataset revisions, exact TRAIN episodes, file sizes and SHA-256 hashes. Metadata is copied byte-for-byte from the source banks; installation does not annotate demonstrations again or prune their contents.

For example, to install Stack Bowls:

```bash
python scripts/fetch_demonstrations.py --task stack_bowls --episodes 0,1,2 \
  --revision 35efbc7dedfdbeeb6e95fb749bd885d73d483e41
python scripts/prepare_task.py --task stack_bowls
```

Use each task's exact revision from the manifest. Stack Blocks uses episodes **0–5**; the other task-specific selections use **0–2**. `prepare_task.py` checks the original HDF5 hashes before installing metadata. It refuses to replace different installed contents. `--task all` installs/checks every task; `--verify-only` reads without installing. `--metadata-only` is for offline software checks and does **not** establish that TRAIN is installed.

## One task, one entry point

```bash
python scripts/run_task.py --task stack_bowls --seed 1 --variant standard --layout 0 \
  --controller delta --model gpt-6-astra --effort xhigh \
  --max-wall-seconds 5400 --output runs/my-stack-bowls
```

This starts a real model/simulator episode. The output directory must be new. Change `--task` to any registered name: `fold_clothes`, `stack_blocks`, `stack_bowls`, `push_T`, `make_toast`, `hang_mugs`, `sweep_blocks`, `pack_objects_into_box`, `pour_liquid_into_cup`, `arrange_largest_number`, `sort_nesting_dolls_by_size` or `store_laptop_and_headphones`.

The entry point selects the published task bank explicitly, including the evaluated six-demonstration Stack Blocks bank. Native step limits are preserved unless an override is deliberately supplied. Historical wall-time limits are 1800 seconds for Fold Clothes, 9000 for packing, and 5400 for the other audited tasks; see [protocols](../resources/published-experiments.json). Task registration and demonstration availability do not imply a completed local evaluation for all 12 tasks.

Push-T supports the optional profiles `baseline`, `summaries`, `no_plan`, `fixed` and `none`:

```bash
python scripts/run_task.py --task push_T --push-simplification none \
  --seed 1 --variant random --layout 0 --model gpt-6-astra --effort xhigh \
  --max-wall-seconds 5400 --output runs/my-push-t-none
```

`prepare_task.py --task push_T` also installs the frozen fixed-reference package. `none` exposes no demonstration-reading tool, although the shared runner still initializes/checks the bank. The profiles simplify policy access, not every deployment dependency.

For a full paired Fold Clothes suite and the existing `--no-rag` control, see [the detailed guide](fold-clothes-reproduction.md). Other tasks can use `scripts/run_rag_batch.py` with an explicit bank, a registered case list and a new output path. Historical launch/audit scripts retain original provenance paths and should not be used as portable setup commands.

## Offline verification

```bash
python scripts/prepare_task.py --task all --metadata-only
PYTHONPATH=src:.runtime/mcp python -m unittest discover -s tests -v
python scripts/build_public_results.py
```

The optional Push-T reference-content integration test requires downloaded TRAIN; four historical MCP checks also require the original development bank. Without those optional data fixtures, five checks are explicitly skipped. The result builder verifies packaged native reports and regenerates Markdown/CSV/JSON without simulation or model calls. Do not use its maintainer-only `--collect-native` option on a normal clone.

No new full native benchmark was run for this integration. Existing model-service failures, simulator interruptions and user-stopped attempts remain in their original reports. Scores from new runs belong to their own frozen configuration.
