# Unified release — 2026-11-11

The release starts from the completed-task integration `7d6294c8dd96062d1509d3d5a9f84599e2935947` and integrates Push-T simplification from `cd86be4f3b5d3f10ceb578cb2365b10113064be3`. The original task worktrees and their frozen runs remain unchanged. The public repository starts with a standalone source snapshot; unpublished historical Git objects and the manuscript are not transferred.

The integrated base already contains Fold Clothes, Stack Blocks, Stack Bowls, Push-T toolkit, Make Toast cells, Hang Mugs tools/guard, Sweep Blocks tools and Pack Objects cells/reference transfer. The remaining four generalization tasks retain their registered generic interfaces. Historical stopped staged controllers are not restored as the current method.

The runtime task modules and original prompt/tool contract fixtures are retained. Release additions provide task-bank installation, a common single-episode launcher, portable source metadata and public evidence exports. Existing tests were adjusted only to remove a machine-config dependency and explicitly mark the TRAIN-dependent reference integration check. Golden contract fixtures were not regenerated.

See [source and protocol manifest](../resources/published-experiments.json) for original runtime and run-registration commits. The [paper table](main-table.md) is transcribed from saved manuscript data and is separate from the [local native evidence](local-results.md). The manuscript itself, TeX sources, PDFs, authentication files, simulator assets and raw TRAIN HDF5 files are excluded.

The [public evidence check](../results/public-evidence-verification.json) covers 400 main-study scenes, 413 original/supplemental attempts, ten Push-T pilot attempts and 62 Stack Bowls model-comparison attempts. It verifies 466 byte-identical native reports. Published records retain source paths and hashes for provenance; those paths are historical records, not installation requirements.

Validation: 175 tests pass with the full local dependencies. A clean source export with third-party code and worker libraries, but no local runtime config or TRAIN data, passes 170 checks and explicitly skips five optional data-dependent checks. Its offline evidence rebuild succeeds. The initial clean check exposed the missing worker-package setup; the guide and pinned worker requirements now document it. No new model/simulator evaluations were launched.
