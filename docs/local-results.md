# Local native evidence

These results belong to the original per-task frozen candidates, **not a fresh run of the merged release**. All tasks use gpt-6-astra / xhigh, seed 1, standard/random layouts 0–24 (25 each). These are known evaluation/development layouts, not a new held-out generalization claim. Steps are native control limits; packing uses 1300, excluding earlier 2000-step development trials.

Confirmed success divides successes by 50 scenes. Unscored scenes are separate from native failures. Supplements fill only originally missing scores; every original interruption remains in the attempt ledger.

| Task | Success | Native failure | Unscored scenes | Confirmed / 50 | All attempts | Retained unscored attempts | Step limit | Runtime source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold_clothes | 37 | 13 | 0 | 74% | 52 | 2 | 500 | `c9f7a99` |
| stack_blocks | 46 | 4 | 0 | 92% | 50 | 0 | 550 | `7fa895e` |
| stack_bowls | 47 | 3 | 0 | 94% | 50 | 0 | 800 | `7fa895e` |
| push_T | 48 | 0 | 2 | 96% | 50 | 2 | 600 | `ead91e4` |
| make_toast | 15 | 35 | 0 | 30% | 53 | 3 | 1400 | `1fe3704` |
| hang_mugs | 13 | 37 | 0 | 26% | 56 | 6 | 800 | `8a954e3` |
| sweep_blocks | 12 | 38 | 0 | 24% | 52 | 2 | 1000 | `ca604e5` |
| pack_objects_into_box | 13 | 37 | 0 | 26% | 50 | 0 | 1300 | `cd82ce5` |

[Summary CSV](../results/local-summary.csv) · [All attempts CSV](../results/local-attempts.csv) · [Scenario ledger](../results/local-scenarios.json) · [Protocol/source manifest](../resources/published-experiments.json). Each scored attempt links to a byte-identical native report and its SHA-256; source reports remain unchanged. Unknown costs in source reports remain unknown.

The paper main table has its own documented reporting scope: see [main table](main-table.md). In particular the local Push-T toolkit run is 48 successful, 0 failed and 2 unscored, not 50/50.

## Push-T simplification pilot

Five profiles each ran one standard-l0 and one random-l0 attempt, seed 1, gpt-6-astra/xhigh, 600 steps / 5400 seconds. This is a ten-attempt development pilot, separate from the 50-scene toolkit run. All five profiles succeeded twice; this does not establish 50-scene non-inferiority or a causal component benefit.

| Profile | Success / attempts | Mean control steps | Mean wall seconds |
| --- | --- | --- | --- |
| baseline | 2/2 | 366.5 | 602.6 |
| summaries | 2/2 | 327.0 | 617.4 |
| no_plan | 2/2 | 302.0 | 610.5 |
| fixed | 2/2 | 384.5 | 554.7 |
| none | 2/2 | 317.5 | 446.7 |

[Native pilot ledger](../results/push-simplification-attempts.json) · [Original report](../results/push-t-simplification-pilot-20261111.json). Default runtime behavior remains the evaluated toolkit; select simplified profiles explicitly.

## Stack Bowls model comparison

Known seed-1 standard/random layouts 0–4, ten scenes per group, xhigh, 800 steps / 5400 seconds. Local implementations and model choices differ from the public leaderboard main table. The study has 60 scenes, 62 attempts, 58 native scores and 2 unresolved scenes; four unscored attempts are retained.

| Local method | Model | Success | Failure | Unscored scenes | Attempts |
| --- | --- | --- | --- | --- | --- |
| linkmind | gpt-6-luna | 0 | 10 | 0 | 10 |
| linkmind | gpt-6-sol | 9 | 1 | 0 | 10 |
| gpt6astra | gpt-6-luna | 0 | 10 | 0 | 11 |
| gpt6astra | gpt-6-sol | 0 | 8 | 2 | 11 |
| hexashell | gpt-6-luna | 9 | 1 | 0 | 10 |
| hexashell | gpt-6-sol | 6 | 4 | 0 | 10 |

[Original study report](../results/stack-bowls-model-comparison-20261109.json) · [Native attempt ledger](../results/stack-model-attempts.json). Paused/stopped FoldClothes, toast and experience-ablation queues are not treated as completed studies.
