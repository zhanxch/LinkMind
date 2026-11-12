# LinkMind — the embodied mode of DeepSeek Harness

Describe a goal in a conversation, watch the agent use robot tools, and guide it while it works. The conversation is DeepSeek Harness's native conversation: its messages, streamed responses, tool calls, attachments and trajectory remain in the same session. The **现场** button opens current simulation observations alongside that conversation. There is no separate embedded workbench or iframe.

This preview extends [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), pinned to `0.2.2-rc.1`, through its preset, model, tool dispatch and client slot APIs. It is a local Web application, not an installed desktop application. The interface additions are in Chinese.

## Product contract

The intended user wants to give an embodied agent a goal, see what it is doing, intervene, and retain useful context for the next attempt. They should not have to assemble an agent architecture before starting. The first supported environment is RoboDojo simulation; arbitrary robots and physical deployment require additional adapters and validation.

- **Conversation is the workspace.** User goals, progress, observable evidence, tool receipts and guidance stay in dsh's native session. Display available reasoning summaries and action explanations, not a promise to expose the model's complete internal reasoning.
- **The scene provides feedback.** Show the current attempt's observations and outcome beside the conversation. A conversation can be interrupted, but an already dispatched action cannot be retroactively edited. Simulator stop is an explicit control; a physical pause/resume protocol is not implemented.
- **Requirements, experience and skills have different meanings.** Requirements describe the desired outcome and constraints. Experiences record what happened under particular conditions, including failures and uncertainty. Skills contain reusable operating instructions. An experience might eventually inform a validated skill; saving or selecting it does not perform that conversion. Temporary corrections remain messages unless the user explicitly asks to remember them.
- **Support is optional.** Selecting a reference asks the agent to consider it. It never forces a procedure. The current profile is fixed for each attempt; an empirically evaluated selector is future work. Infrastructure must not let the agent disable user constraints or physical control limits when it chooses less support.

Success for the first release means completing this collaboration loop reliably: describe a goal → inspect the scene → take bounded actions → receive guidance → report the actual outcome. More panels, compulsory multi-agent roles and automatic self-modification are not release requirements. Needs-first design makes the user contract more stable while capability-dependent support can change; it does not establish immunity to infrastructure half-life. See the [SuperAgent design review](studio-superagent.md) for the proposed evaluation and improvement loop.

## Start the workspace

Requires Linux, Node.js 24.9+ and Python 3.11+. Browsing packaged experience does not require Isaac Sim. Model calls require the selected provider's credentials; the default Codex route reuses a locally installed and logged-in Codex CLI.

From the repository root:

```bash
python3.11 -m venv .venv-studio
.venv-studio/bin/python -m pip install --target .runtime/mcp -r experiments/rag-mcp-requirements.txt
codex login status
cd studio
npm ci
LINKMIND_PYTHON=../.venv-studio/bin/python npm start
```

Open the local URL printed by the launcher. It normally listens on `http://127.0.0.1:3080/`. Existing `~/.dsh` is not changed. Application state, the dedicated dsh profile and development episodes live in `studio/.state/`, excluded from Git. Keep that directory to preserve tasks and conversations. `LINKMIND_STUDIO_STATE` selects another state directory and `LINKMIND_PORT` another port. A simulator requires the assets and ignored `local.runtime.json` described in [reproduction](reproduction.md).

## Work in a conversation

Create a new dsh conversation and select **具身模式 · LinkMind** in its mode menu. Standard and creator modes remain available; LinkMind robot tools belong only to the embodied preset.

1. Describe the desired outcome and any constraints. The agent can inspect the catalog, save a task, and start an explicitly requested simulation. A persistent task retains requirements across attempts; each attempt has its own run ID and native outcome.
2. Open **现场 → 参考经验** to browse historical demonstrations. Read their description, source and uncertainties, then use **引用到会话** to place an explicit reference in the current composer. The agent can inspect the same record with `view_experience(task, experience_id)`. References are evidence, not executable skills or mandatory steps. Full trajectory retrieval still uses native episode tools when the selected profile exposes them.
3. Open **现场** in the session header to inspect an execution's camera image, status and result. The panel's task shortcuts put text into the current composer for review. They do not start an independent agent or silently send a message.
4. During execution, continue writing in the same composer. Use dsh's immediate-send/steer action to deliver guidance at the next agent step, or its queue action for a later turn. An in-flight native action is not retroactively changed. Streamed progress, available reasoning summaries and tool receipts remain visible in the conversation and trajectory.
5. Use **停止仿真** to terminate the simulation. Stopping model generation alone does not stop a simulation. Corrections are ordinary conversation messages; when asked to remember a requirement, the agent can persist it with a link to its source run. There is no separate correction inbox.

The first preview supports one active simulation at a time. A host dispatch hook associates each new task with its native dsh conversation. The scene follows that conversation’s latest attempt; older attempts remain selectable. Robot dispatch checks the conversation assignment before execution. Pre-assignment development records remain on disk but are not silently adopted by a new conversation. This is a single-user continuity boundary, not a multi-tenant authorization system.

## Codex in the native dsh loop

The `linkmind-codex` provider invokes the installed `codex app-server` using native authentication. The model selector is populated from its actual model catalog. `LINKMIND_MODEL` can select a catalog model for new sessions. Other dsh providers can still be selected normally.

The adapter translates dsh's recorded message roles, tool calls/results and image bytes into Codex response items. Each provider request uses an ephemeral Codex thread and replays the dsh request history. Streamed text and available reasoning summaries become native dsh blocks. A Codex dynamic tool request becomes a dsh tool-call block; the provider process stops before dsh executes it. This preserves dsh's existing execution, cancellation, next-step steering and tool rendering. It does not run a second hidden Codex task alongside the chat.

This adapter is experimental and was validated against Codex CLI `0.155.0-alpha.16.3`. It depends on the experimental `thread/inject_items` and dynamic-tool APIs. It reconstructs context per request; it does not resume a separate Codex conversation or promise the latency/cost of a persistent Codex thread. The Codex runtime contributes its own runtime context, so this is a new model/harness configuration. Native authentication stays in Codex; no credentials are copied into this repository. See [Codex app-server documentation](https://learn.chatgpt.com/docs/app-server).

## Execution boundaries

- Every robot call names an explicit `run_id`. An ended attempt cannot redirect to a newer episode. A process lease prevents two Studio services from owning the same state directory, and a call lock serializes robot calls.
- A `call_id` identifies an intended operation. Identical completed calls return their recorded receipt; a reused ID with different arguments is rejected. Transport uncertainty or a native tool error blocks further motion for that attempt. Motion is never automatically replayed.
- The runner supervises the simulator and native MCP process. A parent watchdog interrupts the runner if its service disappears. Stop returns only after runner cleanup exits. This is simulator process control, not a hardware emergency stop or a resumable physical pause.
- dsh authenticates the browser on loopback. Writes require the same browser origin; the internal service separately requires an ephemeral bearer token. This is a single-user local preview, not a multi-tenant robot service.

Native observation, measurement, action and scoring implementations are reused. The legacy CLI remains the default for `scripts/run_task.py`; Studio opts into external-agent mode. The MCP bridge adds task and experience discovery around the existing `task_context`, `episode_tools`, `robot_call`, `finish_episode` and `stop_episode` interface. It preserves original native text/image results and does not manufacture success.

## Needs first, support second

The persistent object is the user's task: desired outcome, preferences, constraints and correction sources. The episode records one model, scene, support configuration and execution. A model upgrade should not erase the task; a restored conversation does not imply a restored physical scene.

Experience access is available for all registered tasks; the existing `none` profile is available for Push-T. That profile retains observation, planar measurement, action execution and geometry/IK safeguards. Support selection is fixed per episode. It does not mean the task requires no infrastructure.

[Design notes from DeepSeek SuperAgent](studio-superagent.md) explain the separation between persistent conversation and concrete execution, the treatment of follow-up messages, and the proposed improvement loop. Router/worker orchestration and automatic infrastructure gating are design directions, not implemented capabilities of this preview.

RSI should propose support changes from recorded outcomes, compare them on fixed paired scenes, and version any accepted change. It must not silently rewrite execution guards or label its own corrections as successful experience. For **Embodied Infrastructure Half-Life**, compare fixed support against the same model's basic interface on matched tasks/scenes/budgets, including failure and overhead. Task-dependent gain decay is a measurable finding; a universal law or an architecture that escapes it has not been established.

## Verify

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_studio.py' -v
cd studio
npm test
```

Tests cover persistence, attribution, process ownership and termination, call deduplication, uncertain outcomes, banks, browser request isolation, native tool translation, image replay, streaming and cancellation. UI and simulator smoke tests are development validation, not benchmarks. Published scores retain their original frozen implementation/protocol provenance.

## Source and attribution

- `studio/launch.mjs`: dedicated profile and process lifecycle.
- `studio/plugin/client.js`: native session header and scene tab.
- `studio/preset.mjs`: embodied mode composition alongside dsh's other modes.
- `studio/plugin/agent.mjs`: native Codex model provider registration.
- `studio/plugin/session.mjs`: host-attributed conversation assignments and dispatch checks.
- `studio/plugin/codex-rpc.mjs`: native Codex transport and request projection.
- `src/roborag/studio/`: persistent tasks, episode service and MCP bridge.
- `src/roborag/rag_runner.py`: optional external-agent mode using the original pipeline.

DeepSeek Harness is copyright DeepSeek under its [MIT license](https://github.com/deepseek-ai/deepseek-harness/blob/main/LICENSE); notices remain in installed packages. Codex is separately installed. Neither credentials nor the private manuscript are redistributed.
