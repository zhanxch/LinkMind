# LinkMind

### A Studio for Embodying Coding Agents

LinkMind brings robot observations, programmable control and interaction experience into a coding agent's working environment. Its **Interaction Experience Harness** connects compact procedural guidance to the original images, robot states and action records. The agent chooses what to inspect, writes actions for the current scene and revises its plan using live feedback.

[Method](docs/method.md) · [Installation and running](docs/reproduction.md) · [Paper main table](docs/main-table.md) · [Native evidence](docs/local-results.md) · [Release provenance](docs/release.md)

## From experience to action

- **Inspect experience on demand.** Retrieve a procedure, then open the source interval behind an operation. Complete TRAIN recordings remain available outside active context.
- **Keep decisions with the agent.** The agent builds its own scene-specific plan, adapts historical references and generates short actions.
- **Close the loop with observations.** Explicit motion checks, execution receipts and fresh RGB/state inform the next decision.
- **Re-evaluate infrastructure as models change.** Support that helps one model or task may add less value for another. Simplification and model studies remain separately reported.

The unified code registers **12 tasks**, integrates the **eight locally evaluated task implementations**, and includes the latest optional Push-T simplification profiles. The original Python namespace remains `roborag` for compatibility. Read the [method explanation](docs/method.md) for the design and its limits.

## Main results

The paper's main table is reproduced below. Each cell is **Score / success rate (%)**, equally averaged over standard and randomized scenes; the final row weights all 12 tasks equally. Bold and underline indicate first and second distinct values per metric. This is the saved paper table, with its published precision and **unreported-task zero-fill convention**, not a new benchmark run of the integrated release.

<!-- MAIN_TABLE_START -->
| Task | WALL-OSS 1.0-lite | VPP2 | OpenWAM-alpha | Pi-05 | PyRUA-Lean | HexaShell-Preview | GPT-6-Astra | LinkMind |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stack bowls | 85.9 / 84.0 | 55.6 / 48.0 | 49.9 / 45.3 | 45.1 / 38.0 | 73.9 / 70.0 | <ins>86.9</ins> / <ins>86.0</ins> | 66.5 / 62.0 | **94.9** / **94.0** |
| Push-T | 3.3 / 3.3 | 1.3 / 1.3 | 0.0 / 0.0 | 0.0 / 0.0 | 86.0 / 86.0 | <ins>96.0</ins> / <ins>96.0</ins> | 60.0 / 60.0 | **100.0** / **100.0** |
| Pack objects into box | 33.2 / 8.7 | 30.4 / 6.7 | 22.5 / 4.7 | 19.1 / 2.7 | **46.0** / **30.0** | 33.1 / 16.0 | 11.6 / 0.0 | <ins>43.5</ins> / <ins>26.0</ins> |
| Fold clothes | **87.5** / **84.7** | 70.8 / 68.0 | 57.5 / 55.3 | 32.3 / 24.0 | 59.2 / 52.0 | 47.6 / 40.0 | 76.4 / 72.0 | <ins>78.0</ins> / <ins>74.0</ins> |
| Hang mugs | 38.8 / 22.7 | <ins>43.9</ins> / **32.0** | 16.3 / 5.3 | 7.3 / 0.0 | 27.7 / 12.0 | 19.0 / 4.0 | 0.9 / 0.0 | **44.7** / <ins>26.0</ins> |
| Sweep blocks | 9.3 / 9.3 | <ins>10.7</ins> / <ins>10.7</ins> | 1.3 / 1.3 | 0.0 / 0.0 | 6.0 / 6.0 | 8.0 / 8.0 | 4.0 / 4.0 | **24.0** / **24.0** |
| Pour liquid into cup | **64.0** / **64.0** | <ins>50.0</ins> / <ins>50.0</ins> | 34.7 / 34.7 | 14.7 / 14.7 | 4.0 / 4.0 | 2.0 / 2.0 | 4.0 / 4.0 | 0.0 / 0.0 |
| Make toast | 26.0 / 13.3 | **50.0** / **39.3** | 12.5 / 2.7 | 6.0 / 0.7 | 21.5 / 14.0 | 1.5 / 0.0 | 0.5 / 0.0 | <ins>37.0</ins> / <ins>30.0</ins> |
| Arrange largest number | 38.2 / 24.0 | 8.3 / 2.0 | 4.9 / 0.7 | 2.8 / 0.7 | **80.1** / **74.0** | 30.2 / 22.0 | <ins>68.7</ins> / <ins>60.0</ins> | 65.7 / 56.0 |
| Sort nesting dolls by size | 48.0 / 48.0 | 18.7 / 18.7 | 4.7 / 4.7 | 5.3 / 5.3 | <ins>70.0</ins> / <ins>70.0</ins> | 52.0 / 52.0 | 18.0 / 18.0 | **82.0** / **82.0** |
| Store laptop and headphones | **50.4** / <ins>22.0</ins> | <ins>45.3</ins> / **32.7** | 30.5 / 16.0 | 16.1 / 5.3 | 4.8 / 0.0 | 4.8 / 0.0 | 1.6 / 0.0 | 0.0 / 0.0 |
| Stack blocks | 75.2 / 71.3 | 51.7 / 44.7 | 13.7 / 7.3 | 11.9 / 6.7 | **100.0** / **100.0** | 89.5 / 88.0 | 88.1 / 86.0 | <ins>93.2</ins> / <ins>92.0</ins> |
| Mean (12 tasks) | 46.7 / 37.9 | 36.4 / 29.5 | 20.7 / 14.8 | 13.4 / 8.2 | <ins>48.3</ins> / <ins>43.2</ins> | 39.2 / 34.5 | 33.4 / 30.5 | **55.3** / **50.3** |
<!-- MAIN_TABLE_END -->

**Reporting scope:** the paper's Push-T 100/100 differs from the archived local toolkit run (48 successes, 2 unscored scenes); Arrange Largest Number and Sort Nesting Dolls use author-supplied paper values; two unreported tasks are filled with zero for the paper mean. The table is from saved manuscript commit `f0f352e`; an authenticated online refresh was unavailable. See [table notes and CSV](docs/main-table.md) and [local attempt-level results](docs/local-results.md) for the exact distinctions. Baselines and local runs are not seed-matched. The manuscript, TeX and PDFs are not included.

## Run a task

First complete the [runtime and demonstration setup](docs/reproduction.md). Then use one entry point:

```bash
export PYTHONPATH=src:.runtime/mcp
python scripts/run_task.py --task stack_bowls --seed 1 --variant standard --layout 0 \
  --controller delta --model gpt-6-astra --effort xhigh \
  --max-wall-seconds 5400 --output runs/my-stack-bowls
```

Task names and frozen bank manifests are in [resources/task-bundles.json](resources/task-bundles.json). Install a task bank with `python scripts/prepare_task.py --task TASK`; it verifies downloaded TRAIN hashes and never re-annotates the experience. Run outputs use new directories so previous evidence is preserved.

## Verify the release

```bash
python scripts/prepare_task.py --task all --metadata-only
PYTHONPATH=src:.runtime/mcp python -m unittest discover -s tests -v
python scripts/build_public_results.py
```

The checks run offline. Optional data-dependent checks require TRAIN or the historical development bank. The public evidence package contains **466 native scoring reports**, plus source reports, SHA-256 hashes, failures, interruptions and missing-score supplements. [CSV and JSON exports](docs/local-results.md) can be regenerated from the packaged evidence. Full native evaluation of the merged release has not been rerun.

## Code map

- `src/roborag/rag_tasks.py`, `prompts/`: registered tasks and task-specific instructions.
- `src/roborag/rag_runner.py`, `rag_sim.py`: agent, MCP and simulator lifecycle.
- `src/roborag/mcp/`: observation, retrieval, references, plan, actions and task tools.
- `resources/`: frozen experience metadata, TRAIN manifests and publication sources.
- `experiments/`, `results/`: registered protocols, reports and auditable outcomes.

This project builds on [RoboICL](https://github.com/Mosi-AI/RoboICL), [RoboDojo](https://robodojo-benchmark.com/) and [HexaShell](https://github.com/HexaFuture/HexaShell). Third-party runtimes, assets and datasets retain their respective licenses and installation requirements.
