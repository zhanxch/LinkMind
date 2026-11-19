# Agent RSI Board 与环境注册

在 DSH 的具身模式中打开工作区，点击左侧 **环境注册** 或 **Agent RSI Board**。注册的环境供本机同一 Studio profile 的项目复用。Board 按工作区汇总，同一项目换一个会话仍能看到之前的迭代。

## 第一次看两轮改动

打开 `examples/studio-project` 工作区，在会话中说「运行 rsi-calibration」，然后打开 **Agent RSI Board**，选择 `mean_absolute_error`。校准脚本先用原控制器测量四个固定目标的误差，再用测得的平均偏差修正控制器，重复相同测量。点击 **查看运行** 可以回到此次执行。这个演示使用 Python 标准库，两轮都实际计算，无需 GPU、模型账号或仿真器。

曲线的横轴是迭代代数。两个分支都从第一轮修改，就会落在同一代。表格保留每轮版本、修改、假设、决定、状态、指标和相对父轮的差值。缺少测量时显示空值，父轮缺失、重复或形成循环时保留记录并标记关系待核对。运行过程中会定时刷新。

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
