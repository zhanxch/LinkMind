# LinkMind

### A Studio for Embodying Coding Agents

Model progress can change which support is load-bearing. OpenAI's [FDE team](https://openai.com/index/forward-deployed-engineering-means/) calls it progress when a model can handle use cases that once took months of custom engineering; Codex engineer Thibault Sottiaux describes a harness as scaffolding to remove over time in a [podcast interview](https://linearb.io/dev-interrupted/podcast/openai-codex-thibault-sottiaux-agentic-autonomy). [Anthropic's account](https://www.anthropic.com/research/harness-design-long-running-apps) says harness components encode assumptions that can go stale: after Opus 4.6, sprint decomposition was unnecessary for some work, while evaluation still helped near the model's capability edge. Its follow-up on [Managed Agents](https://www.anthropic.com/research/managed-agents) proposes stable interfaces that let implementations change.

The half-life metaphor has appeared in earlier writing on scaffolding ([example](https://theintelligenceengine.com/p/the-scaffolding-has-a-half-life)); LinkMind uses it for a specific robotics quantity, **Embodied Infrastructure Half-Life**: how the gain from a fixed support configuration changes across models, measured against each model's basic robot interface on the same tasks, scenes and budgets. The half-life point is reached when that gain falls to at most half its initial value; a model upgrade alone does not establish that it has. **LinkMind Studio** makes the question concrete: its **Interaction Experience Harness** links procedures to original demonstrations that an agent can inspect, adapt to the current scene and check against live robot feedback.

> **What support should an embodied agent retain, revise or remove as models and task requirements evolve?**

[Method](docs/method.md) · [Installation and running](docs/reproduction.md) · [Paper main table](docs/main-table.md) · [Native evidence](docs/local-results.md) · [Release provenance](docs/release.md)

## Key ideas

### Embodied Infrastructure Half-Life

A tool, skill or harness that helps one model may contribute less after a model upgrade, while more demanding tasks can create new support needs. We study this possible decline through the **incremental gain over the same model's basic robot interface**, holding the support configuration, scenes and evaluation budget fixed. A positive gain has halved when a later model retains at most half that gain, even if absolute task performance improves. This is a question to measure for each setting, rather than an assumed universal decay law. See the [design rationale](docs/method.md#the-design-question) and [cross-model study](docs/local-results.md#stack-bowls-model-comparison).

### LinkMind Studio

The studio brings **robot tools, reusable skills and execution feedback** into the coding agent's working environment through **Model Context Protocol (MCP)**. Explicit interfaces expose live RGB and robot state, declare control conventions and accept bounded action chunks. The agent owns the current plan: it chooses objectives, writes actions and revises its decisions after inspecting execution receipts and fresh observations.

### Interaction Experience Harness

The harness makes demonstrations inspectable at the level the agent needs:

- **Source-linked experience.** Each procedural phase points to its original recording interval, preserving the connection between a described operation and its images, robot states and action records.
- **Progressive disclosure.** Retrieve a compact procedure, then expand selected windows for state summaries, gripper events, images or numerical actions. Complete TRAIN recordings remain available outside active context.
- **Scene-specific adaptation and live feedback.** Use historical evidence to construct new actions for the current scene, then inspect what actually happened. The agent can combine, skip or reorder demonstrated operations.

**Default interaction loop:** Observe → retrieve and inspect experience → record a current plan → execute a short action chunk → inspect feedback and revise.

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
