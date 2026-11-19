# visual RSI studio examples

Open this directory as a DSH workspace and select **具身模式 · visual RSI studio**. Open **Agent RSI Board** for the RoboDojo batch overview (eight tasks, 400 scenes from the frozen historical reports). Switch experiments to compare five human-authored Push-T tool ablations on two development layouts. Select **no_plan** with **summaries** as the parent. Both layouts still pass. Their step counts move in opposite directions. Click a layout to inspect both recorded tool sequences and native verdicts in the evidence files.

The ten historical reports use the frozen candidate cd86be4f and the 2026-11-11 planning protocol. This paired development pilot measures neither autonomous RSI nor held-out generalization. No simulation or model call is made when opening these files. Both runnable recipes use the Python standard library.

- Ask the agent to run `rsi-calibration` and open **Agent RSI Board**. The script measures a scalar controller's tracking error over two rounds on the same targets. It logs real measurements and the parent round. It uses a deterministic controller and calls no model.
- Ask the agent to run `smoke` and open **控制会话与摄像头**. A synthetic blue dot exercises incremental logs, frame updates and JSON output.

Each launch gets its own `LINKMIND_RUN_OUTPUT` directory. The calibration recipe writes one JSON line per round to `rounds.jsonl`; the smoke recipe atomically replaces `frame.png`. Edit the recipes in `linkmind.studio.json`.
