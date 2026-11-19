# Agent RSI Board 与环境注册

在 DSH 的具身模式中打开工作区，点击左侧 **环境注册** 或 **Agent RSI Board**。注册的环境供本机同一 Studio profile 的项目复用。Board 按工作区汇总，同一项目换一个会话仍能看到之前的迭代。

## 第一次打开

打开 `examples/studio-project` 工作区，点 **Agent RSI Board**。随包附带 Push-T 五档工具消融的十次历史执行，打开即可查看。每档在同样的两个开发布局上测试一次。每个版本都按预先制定的人工改动标注；这份数据可以检验评估视图，无法验证 Agent 自主改进或留出集泛化。

选择 **no_plan**，保留父版本 **summaries**。两种布局都成功。标准布局从 455 步降至 342 步，随机布局从 199 步升至 262 步。点击一个布局，查看实际工具调用次数，再打开该次证据，按序查看工具调用及原生评分。两个布局都只有一对试次，单次步数差没有隔离随机波动。[冻结协议](https://github.com/zhanxch/LinkMind/blob/270175a/experiments/push_T/simplification-pilot-20261111.json) · [原始汇总](https://github.com/zhanxch/LinkMind/blob/270175a/results/push-t-simplification-pilot-20261111.json)

## 复盘一轮改动

先看**为何改、谁改、改了什么**。有记录时，Board 展示触发反馈、来源试次、假设和保留或回滚的决定。再看**哪些试次改变了结果**。选择父版本或同协议的其他版本，按试次比较修复、回归、两版都失败和两版都成功。新增、缺席、条件改变、中断和未评分分别保留。分母显示本版实际记录的例数，配对数只包含两边都有明确判定且条件一致的试次。

点一个场景查两版的失败描述、工具次数和证据。可切换查看步数、耗时或记录的其他执行代价。对托管运行可打开实际控制会话及摄像头。下方 **版本谱系与标量趋势** 保留原始曲线。只有标量的旧记录仍能查看。

## 注册本机环境

1. 在 **环境注册** 选择环境代码目录。填写运行该环境的 Python 绝对路径。留空时优先使用 checkout 内的 `.venv/bin/python`，其次使用服务解释器。
2. 点击 **注册环境**。Studio 识别适配器，记录目录和解释器，并列出缺失的包、入口或资产。**检查环境** 可以重新检查和查看任务；**编辑绑定** 可更新路径和解释器。为同一环境的多个版本取不同的注册名即可并存。
3. 选中环境，点击 **添加观察配置 → 打开运行配置**，启动 `observe-环境名`。内置观察器重置一个场景，写入 `observation.json` 和 `view.png`。去 **控制会话与摄像头** 看这次的画面。可以在运行配置里修改任务、套件和种子。

适配器使用各自 checkout 中的原生入口。此次验证范围如下。

- **LIBERO** 使用 OffScreenRenderEnv，在 libero_spatial 完成真实场景重置并取得 RGB 帧。[上游版本](https://github.com/Lifelong-Robot-Learning/LIBERO/tree/8f1084e3132a39270c3a13ebe37270a43ece2a01)
- **LIBERO-Pro** 单独绑定其代码与 Python，在 libero_spatial_with_mug 使用扰动物体资源完成重置并取得 RGB 帧。[上游版本](https://github.com/Zxy-MLlab/LIBERO-PRO/tree/eafdb809426b13153aa1e4c42d6601844217dfec)
- **RoboCasa** 从官方任务目录读取原子与复合任务，观察器调用 create_env，默认 OpenDrawer、target split。本次核对了入口与配置，本机缺少完整运行依赖及模型资产，尚未取得原生画面。[上游版本](https://github.com/robocasa/robocasa/tree/7bfc60c9d26c02506d4265cbe0e86b35e6e25d42)
- **RoboTwin 2** 读取本地任务，使用原生任务配置、setup_demo 和头部相机。默认 beat_block_hammer、demo_clean。本次核对了入口与配置，本机缺少 SAPIEN、运动规划依赖与资产，尚未取得原生画面。[上游版本](https://github.com/RoboTwin-Platform/RoboTwin/tree/ea8b21121ebb3cd201ff5b3fe361944ac94eda3f)

注册与依赖检查不安装第三方包。正式策略评估请使用方案自己的启动程序、初始状态与评分协议。将 `"environment":"libero"` 加入已有 recipe，便可在 argv、env 和 checks 中使用 `{env.root}`、`{env.python}`。每次运行保存注册记录的指纹、环境目录、解释器和可取得的 Git 提交。数据集、包版本及本地资源差异需要在实验协议中另行记录。

## 接入新环境

在新环境仓库根目录添加 `studio.environment.json` 和一个可执行观察逻辑的 Python 文件，无需修改 Studio。

```json
{"version":1,"id":"my-sim","observe":"observe.py","required":["assets"],"packages":["numpy"]}
```

`required` 是相对环境根目录的路径，`packages` 使用顶层 Python 导入名。观察脚本使用选定的 Python 启动，从 `RSI_ENV_ROOT` 读取环境目录，在 `LINKMIND_RUN_OUTPUT` 下创建输出目录、写入 `view.png` 和 `observation.json`。注册后使用与内置适配器相同的检查和运行入口。

## 把自己的 Agent 接入 Board

一个独立运行代表一轮时，在策略的 recipe 中增加 `"rsi":{"series":"grasp-policy","protocol":"heldout-v1","id":"base","agent_version":"v1","change":"初始版本"}`。下一轮换一个 id，填入 `"parent":"base"`，注明改动。Board 自动读取原生结果中的 `native.score`（如有）和运行耗时。重复执行需使用新的轮次 id 或不同的 series。

同一次执行内有多轮时，在 recipe 添加 `"rsi_events":"rounds.jsonl"`，每次评估后向本次输出目录的该文件追加一行 JSON 并 flush。独立在 Studio 外运行也支持同一格式，写到工作区根目录的 `studio.rsi.jsonl` 即可。基线和后续版本共用 series 与 protocol。

```jsonl
{"version":1,"series":"grasp-policy","protocol":"heldout-v1","id":"r0","agent_version":"v1","change":"初始策略","conditions":{"suite":"heldout","seeds":"0-9"},"metrics":{"success_rate":0.4,"tool_calls":24}}
{"version":1,"series":"grasp-policy","protocol":"heldout-v1","id":"r1","parent":"r0","agent_version":"v2","hypothesis":"抓取前校准可减少偏移","change":"增加一次视觉校准","decision":"保留并扩大验证","conditions":{"suite":"heldout","seeds":"0-9"},"metrics":{"success_rate":0.6,"tool_calls":27}}
```

上面两行是格式示意。指标由实验程序实测，支持任意命名的有限数值。独立程序可使用标准 JSONL，或导入 `roborag.studio.rsi_board.log_round(path, **fields)`。可比条件包括显式 protocol、conditions，以及托管运行记录的环境绑定与提交、时限和任务、种子、预算等元数据。只在同组内连接明确的父轮。对于外部记录，请在 conditions 明确写入环境版本、评估集、预算和人工介入条件。只有 Studio 托管运行才具备返回运行的链接；可查看的控制事件和摄像头取决于该运行实际提供的产物。

## 记录逐例反馈

`episodes` 是轮次记录的可选字段。每条试次提供稳定的 `id` 与 `outcome`（success、failure、unscored、interrupted）。同一 id 跨版本代表相同任务、种子、布局和尝试编号；重复评估用不同尝试编号。`setup` 可存布局或输入摘要，`split` 可标记开发集或留出集。两边 setup 或 split 不同的试次单列。明确上报零才能区分“用过零次”和“缺数据”。

```json
{
  "series":"grasp","protocol":"heldout-v1","id":"v2","parent":"v1",
  "author":"agent","trigger":"上一版侧抓时滑落","trigger_case":"cup/seed7/try1",
  "hypothesis":"夹持后复测能提前发现滑动","change":"在抬升前加入复测",
  "episodes":[{"id":"cup/seed7/try1","label":"杯子 · seed 7","split":"开发集",
    "setup":"layout-A","outcome":"success","cost":{"steps":74,"interventions":0},
    "tools":{"measure":3},"evidence":"reports/v2/cup7.json"}]
}
```

这是接入格式。author 可选 agent、human、unknown；只有观察到的来源和实际做出的决定才写入。evidence 为工作区内可打开的相对文件。标记了 rsi 的托管运行会尝试从原生逐例成功标记或显式 scored/success 判定读取结果。整次运行的耗时与步数只归给单例报告。每个实验仍需明示协议、预算和数据集；Board 无法从轨迹推断修改的作者或因果效果。
