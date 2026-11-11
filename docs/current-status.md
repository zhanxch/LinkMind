# Public release status — 2026-11-11

Unified LinkMind snapshot: completed-task integration `7d6294c` plus optional Push-T simplification `cd86be4`. All 12 registered task banks are packaged with checksums and a common launcher. Default evaluated task contracts remain intact; the unified release has not undergone a new complete native evaluation.

The public [paper main table](main-table.md) follows the saved manuscript `f0f352e` and its explicit author/zero-fill conventions. The [local evidence table](local-results.md) independently preserves failures and missing scores. The manuscript itself is excluded. See [release provenance](release.md) and [setup](reproduction.md).

---

# 当前版本与证据

2026-11-08：集成分支 `integration/completed-tasks-20261108`，以 `codex/pack-box-tools` 的 `6e7ea1c` 为基础，合入 `feat/push-t-toolkit-20261103` 的 `50fcf82` 和 `codex/hang-mugs-tools` 的补测记录 `46b1b13`。其他任务实现已在装箱分支的祖先中。

当前执行方式为完整示范按需检索、模型自己的 `record_plan`、短动作段及当前反馈。任务代码已收束；集成兼容检查不构成新的原生评测。

## 冻结候选与原生结果

- **fold_clothes：37/50，74%**。原分支 `refactor/v3-evidence-context`，候选 `c9f7a99`。[首轮协议](../experiments/fold_clothes/v3-evidence-context-20261028.json)、[补测协议](../experiments/fold_clothes/v3-evidence-context-20261029-unscored-retest.json)、[最终逐例结果](../results/v3-evidence-context-fold-20261029-merged-final.json)。50 个唯一场景，补测 2 个未评分场景，实际 52 次尝试。
- **stack_blocks：46/50，92%**；**stack_bowls：47/50，94%**。原分支 `refactor/v3-generalization`，候选 `7fa895e`。[协议](../experiments/generalization/remaining-v3-20261029.json)、[积木结果](../results/generalization-stack_blocks-first-pass-final-20261029.json)、[叠碗结果](../results/generalization-stack_bowls-first-pass-final-20261029.json)。
- **push_T：48 成功、0 原生失败、2 未评分**。原分支 `feat/push-t-toolkit-20261103`，候选 `50fcf82`，运行实现与 `ead91e4` 一致。[协议](../experiments/push_T/toolkit-v1-full50-20261104.json)、[原生结果](../results/push-t-toolkit-v1-full50-20261104.json)、[独立核验](../results/push-t-toolkit-v1-full50-independent-audit-20261104.json)。600 步，未评分未补测，不能写成 50/50。
- **make_toast：15/50，30%**。记录分支 `codex/make-toast-reliability`，完整评测登记 `b4ace31`，运行实现 `1fe3704`。[协议](../experiments/make_toast/python-cells-full50-20261104.json)、[最终覆盖](../results/make-toast-python-cells-full50-coverage-20261105.json)。53 次尝试，含 3 个原未评分场景的补测。
- **hang_mugs：13/50，26%**。记录分支 `codex/hang-mugs-tools`，候选 `8a954e3`。[协议](../experiments/hang_mugs/guard-v2-full50-20261105.json)、[最终覆盖](../results/hang-mugs-guard-v2-full50-supplement-coverage-20261106.json)。56 次尝试，含 6 个原未评分场景的补测。
- **sweep_blocks：12/50，24%**。记录分支 `codex/sweep-blocks-tools`，候选 `ca604e5`。[协议](../experiments/sweep_blocks/tools-v1-full50-20261106.json)、[最终覆盖](../results/sweep-blocks-tools-v1-full50-supplement-coverage-20261107.json)。52 次尝试，含 2 个原未评分场景的补测。
- **pack_objects_into_box：13/50，26%**。记录分支 `codex/pack-box-tools`，候选 `cd82ce5`。[协议](../experiments/pack_objects_into_box/tools-v1-native-full50-20261107.json)、[原生结果](../results/pack-box-tools-v1-native-full50-20261107.json)、[关闭核验](../results/pack-box-tools-v1-native-full50-closure-20261107.json)。50 次尝试，原生 1300 步；早期 2000 步开发结果另列。

上述场景均为既有 seed 1 布局；结果不作独立留出泛化或检索收益的因果证明。报告里的绝对路径保留实验来源，不是其他机器的安装路径。新实验按 [Foldclothes 复现指南](fold-clothes-reproduction.md) 建立自己的输出目录和版本记录。
