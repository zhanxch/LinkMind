# visual RSI studio examples

Open this directory as a DSH workspace and select **具身模式 · visual RSI studio**. Both recipes use only the Python standard library.

- Ask the agent to run `rsi-calibration` and open **Agent RSI Board**. The script measures a scalar controller's tracking error over two rounds on the same targets. It logs real measurements and the parent round. It uses a deterministic controller and calls no model.
- Ask the agent to run `smoke` and open **控制会话与摄像头**. A synthetic blue dot exercises incremental logs, frame updates and JSON output.

Each launch gets its own `LINKMIND_RUN_OUTPUT` directory. The calibration recipe writes one JSON line per round to `rounds.jsonl`; the smoke recipe atomically replaces `frame.png`. Edit the recipes in `linkmind.studio.json`.
