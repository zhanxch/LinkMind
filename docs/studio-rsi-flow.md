# Agent RSI Board 的演化流程

打开具身模式工作区，然后打开 **Agent RSI Board**。默认页实时显示一轮里正在处理的证据、并行候选各自走到哪一阶段、被拒原因和生效版本。点节点打开假设、检查结果与原文件。右上角 **批量评测** 打开同一个工作区的任务 × 版本矩阵。

## 本机演示

在示例工作区运行配置 `rsi-workflow-demo`。它实际运行八个本地 Python 测试。A 保序去重，B 硬编码评测输入而被审查拒绝，C 排序后改变了原顺序而在回归测试后淘汰。可从正在执行的评估观察「已测」计数。评估完成后显示真实通过数。最终采用的代码和三个候选的差异均写到工作区的 `.studio-rsi`。演示无需模型与机器人。

## RRSI 探针

基于上游 `be50316e`。观察器保留原 CLI 的参数和评估方式。完整 `run` 及单轮 `round` 均可用。逻辑围绕 `Run.round`、`_draft`、`_evaluate`、`select_round` 和最终 frontier 文件打点。探针支持通用演化工作区，直接在 RRSI checkout 里运行。上游仍需它自己的安装、模型账号和评测环境。[核对过的上游](https://github.com/google-research/rrsi/tree/be50316e1db05914068a973f322770ef08ed7ba1)

```sh
# 在 RRSI checkout。BACKEND_SRC 使用 Studio 安装内的 backend/src。
PYTHONPATH="$BACKEND_SRC" python -m roborag.studio.rrsi_probe ./rrsi.py --domain coding run
```

同一 checkout 有多个独立实验时，设不同的 `RSI_FLOW_RUN`。默认追加到当前工作区的 `studio.rsi.events.jsonl`。可以通过 `RSI_FLOW_PATH` 改到工作区内的其他文件并在 sources 清单中登记。代码差异和原生评估文件必须位于事件文件所在工作区内，Studio 才能打开它们。分析者请求诊断的试次、提议者请求读取的轨迹和写入的文件来自原生 JSON 动作。候选完成后的实际改动以 diff 为准。上游工作树和依赖由 RRSI 管理。

RRSI 的审查节点包含泄漏检查与运行自检。候选通过审查后才出现在评估列。选择节点展示实际分数、token 变化、噪声调整下限、成本规则和域约束。评估阶段会预告计划试次，上游任务尚未写出逐例进度时显示进行中，原生报告到达后显示覆盖。只有 frontier 确认采用版本时，生效列才标为已生效。

## OpenRSI 凭据

在 OpenRSI 验证工作区新建 `studio.rsi.sources.json`，路径相对该工作区：

```json
{"version":1,"sources":[{"kind":"openrsi","label":"倒水 · 第一轮","path":"outputs/pour-round1"}]}
```

适配器读取 scheduler、试次账本、学习状态和冻结凭据。打开节点可查看提案、原版与启用后的配置、评估结果索引。卡在取样时只显示实际取样和停止原因。经验学习、配置冻结、复测各有独立状态。旧格式里没有独立采用凭据时，生效列保持空白。

## 原生事件

也可直接写 JSONL，或从 Python 导入 `roborag.studio.rsi_flow.emit(path, ...)`。一条记录只更新一个轮次中的一个节点。

```json
{"schema":1,"run":"coding-rsi","round":2,"stage":"proposal","candidate":"A","status":"done","workflow":"coding","focus":"处理反复出现的恢复失败","change":"增加有界校验","links":[{"label":"候选差异","path":"runs/r2/A/diff.patch"}]}
```

阶段为 `round`、`evidence`、`proposal`、`review`、`evaluation`、`decision`、`activation`。整轮使用 `stage=round`。无 candidate 的事件显示在整轮行。节点可附带 `focus`、`hypothesis`、`change`、`reason`、`version`、`progress`（done/total）、`metrics`、`checks` 和工作区内文件链接。还可以通过 `studio_run` 指向对应的 Studio 运行，打开控制会话和摄像头。

可用状态为 running、done、passed、rejected、admissible、adopted、retained、blocked、failed、skipped。用 agent 明示的假设和实际证据编号记录关注点。由真实的文件写入、评估器判定和版本变更触发后续状态。服务推送变更快照，断线重连从完整快照恢复。
