# LinkMind in DeepSeek Harness Desktop

LinkMind adds **具身模式 · LinkMind** to the existing DSH mode menu. Use the normal DSH conversation to describe a goal, watch streamed responses and tool calls, and send guidance while the agent works. The **摄像头** button opens a camera tab in DSH’s existing right sidebar. There is no additional chat application or agent loop.

This version focuses on the basic collaboration loop: conversation → robot tools → live images → user guidance. Experience browsing, saved corrections, long-term memory, RSI and automatic infrastructure selection are outside this version. The underlying research implementations remain available through their existing CLI interfaces.

## Installation

Use [DSH Linux Desktop](https://github.com/zhanxch/dsh-linux), based on official DSH `0.2.2-rc.2`. The LinkMind bundle is pinned to that host version. Install Node.js 24.9+ with npm and prepare the simulation checkout using [reproduction.md](reproduction.md): the assets, HexaShell checkout and ignored `local.runtime.json` must point to working simulation and policy interpreters. Install `experiments/rag-mcp-requirements.txt` into `.runtime/mcp` using the configured policy Python (3.11+).

Open DSH Desktop once to initialize its profile, then fully quit it. From the LinkMind repository root:

```bash
node studio/install-desktop.mjs
```

The installer finds the installed Linux Desktop CLI, packs the plugin, installs it through DSH’s own bundle manager, and adds the LinkMind checkout path to the existing profile. Account credentials, model defaults and conversation files are preserved. Profile backups are saved under `$DSH_HOME/linkmind-install-backups`. The default home for this community desktop is `~/.local/share/dsh-linux/home`; use `--home /path/to/DSH_HOME` and `--dsh /path/to/dsh` for another installation. The checkout remains a runtime dependency; keep it at the configured path.

Reopen **DeepSeek Harness** from the application menu. Select **具身模式 · LinkMind** in a new conversation. No browser needs to be opened, and the service starts and stops with the desktop host.

## Work in the normal conversation

1. Select a model using DSH’s usual model menu. The desktop plugin uses the existing provider and login. Describe a task and request execution, for example: “启动一个 Push-T 仿真，使用最简配置。先观察场景，告诉我准备怎么做。”
2. Read streamed responses and native tool calls in the conversation. LinkMind exposes task creation, episode startup, context, available robot tools, robot calls, finish and stop through MCP. Task-specific observation, measurement and bounded action tools retain their native schemas and image results.
3. Click **摄像头** in the conversation header. Switch between head, left wrist and right wrist images. The panel follows this conversation’s latest attempt, shows the control step and frame age, and keeps the last frame when a connection drops.
4. During execution, type in the same composer. Use DSH’s normal immediate-send/steer control for guidance at the next agent step, or its queue control for a later turn. LinkMind does not replace these controls. An already dispatched action segment finishes before new guidance can affect subsequent actions.
5. Click **停止仿真** to end the simulation. Cancelling model generation alone does not terminate a simulator. The camera stop control is an explicit process stop, not physical pause/resume or a hardware emergency stop.

The first environment is RoboDojo simulation, with one active simulation at a time. A host tool hook binds tasks to the native conversation identity and checks it before robot execution. Completed or interrupted runs retain their own IDs; they cannot silently redirect commands to a new episode.

## Camera behavior

Studio opts into display-only RGB snapshots at up to four updates per second during native action execution. All three views are published with atomic file replacement. Between action segments the simulation does not advance; the panel honestly shows the age of the latest image rather than pretending a static frame is live video. Camera rendering adds wall-clock overhead but does not dispatch control steps or change the native score.

The sidebar receives snapshot updates over a reconnecting stream. Each connection starts with current state, including a final result when available. Dropped streams do not replay robot commands. A display failure preserves the previous frame and does not turn a completed action into an execution error. Use **重试画面** if an image failed to load.

## Runtime and model ownership

The plugin runs the local Python service as a child of the desktop host. It uses a private connection descriptor and an ephemeral bearer token. Closing the host terminates its service and owned simulator; an owner watchdog also handles unexpected host loss. State is stored under `$DSH_HOME/linkmind` by default. Do not delete that directory to retry a failed operation.

The built-in DSH conversation owns messages, streaming, tool execution, steering, cancellation and the transcript. The optional `codex` plugin setting registers the existing experimental `linkmind-codex` provider without changing the desktop’s default model. That adapter uses an installed, logged-in Codex CLI and replays DSH history through experimental app-server APIs; it is not required for the desktop’s normal provider.

Robot calls name an explicit `run_id` and `call_id`. Identical completed calls return their original receipt. Reusing an ID with different arguments is rejected. An uncertain or errored action blocks further motion until the attempt is stopped; actions are not automatically retried. Only the native result establishes the benchmark outcome.

Desktop requests pass through DSH authentication. Browser writes require the same origin; the desktop protocol forwards its authenticated cookie and a custom request header. The internal Python endpoint separately requires its token. This is a local, single-user application.

## Development preview and checks

An optional Web preview runs the same plugin in an isolated `linkmind-basic` profile. It is a development route, not the desktop launch method:

```bash
cd studio
npm ci
npm start
```

It keeps state in `studio/.state/` and uses the experimental local Codex provider. `LINKMIND_STUDIO_STATE`, `LINKMIND_PORT` and `LINKMIND_PYTHON` select development state, port and interpreter. Existing desktop credentials are not copied.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_studio*.py' -v
cd studio
npm test
```

Development verification includes service lifecycle, conversation ownership, non-replayed motion, basic MCP tools, desktop request authentication, camera throttling/failure recovery, and native action/score compatibility checks. A real Push-T smoke test verified that frames updated during a 24-step hold, two original tool images were returned, and stop released the simulator. The first malformed hold request was rejected before motion and retained; neither attempt is a benchmark.

The installed bundle was checked in a separate DSH profile and all modes loaded without diagnostics. Automated visual inspection of the assembled desktop UI remains incomplete because the available browser tool rejected the local test address. This includes light/dark appearance, narrow sidebar layout and interactive steering in the rendered UI; source checks and backend tests do not establish those visual results.

## Source

- `studio/install-desktop.mjs`: DSH bundle installation and profile preservation.
- `studio/plugin/desktop-host.mjs`, `runtime.mjs`: plugin configuration, service lifetime and mode registration.
- `studio/plugin/client.js`: camera header button and native sidebar tab only.
- `studio/plugin/preset.mjs`, `session.mjs`: embodied mode and conversation ownership.
- `src/roborag/studio/`: episode service, camera publication and MCP bridge.

DeepSeek Harness is copyright DeepSeek under its [MIT license](https://github.com/deepseek-ai/deepseek-harness/blob/main/LICENSE). The LinkMind DSH plugin carries its own MIT notice. Credentials, machine configuration and the private manuscript are not redistributed. Published experimental scores keep their original frozen implementation and protocol provenance.
