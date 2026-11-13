# LinkMind in DeepSeek Harness Desktop

LinkMind adds **具身模式 · LinkMind** to the existing DSH mode menu. Use the normal DSH conversation to describe a goal, watch streamed responses and tool calls, and send guidance while the agent works. The **运行与摄像头** button opens a camera tab in DSH’s existing right sidebar. There is no additional chat application or agent loop.

Bundle `0.4.0` supports both built-in interactive simulation and [external project development](studio-projects.md): open a repository, prepare an environment, save a recipe, run its original program, modify it and compare raw records. **项目与配置** beside the native workspace/mode picker discovers saved configurations, opens files, edits launch JSON and runs the selected configuration. It can create a default Studio workspace or add an existing repository to DSH's workspace list. The normal conversation remains the primary interface. Experience browsing, saved corrections, long-term memory, RSI and automatic infrastructure selection are outside this version. Imported methods execute through their own CLI and policy; they are not replaced by the conversation agent.

The independently installable project-workbench bundle is distributed at [dsh-linkmind-studio](https://github.com/zhanxch/dsh-linkmind-studio). It includes the local project service and needs no simulator for configuration browsing or the synthetic example. This checkout is still needed for the optional built-in LinkMind simulation route. Control/activity visualization is a separate experiment, not part of this release.

## Installation

Use [DSH Linux Desktop](https://github.com/zhanxch/dsh-linux), based on official DSH `0.2.2-rc.2`. The LinkMind bundle is pinned to that host version. Install Node.js 24.9+ with npm and Python 3.11+. Install `experiments/rag-mcp-requirements.txt` into `.runtime/mcp` using that Python. This is enough for the Studio service and the [integration example](studio-projects.md#try-the-workflow-without-a-simulator); external projects prepare their own environments. To use the built-in simulation, also follow [reproduction.md](reproduction.md): assets, the HexaShell checkout and ignored `local.runtime.json` must point to working simulation and policy interpreters. The plugin's `python` setting can select the service interpreter; otherwise it uses `local.runtime.json` or `python3`.

Open DSH Desktop once to initialize its profile, then fully quit it. From the LinkMind repository root:

```bash
node studio/install-desktop.mjs
```

The installer finds the installed Linux Desktop CLI, packs the plugin, installs it through DSH’s own bundle manager, and adds the LinkMind checkout path to the existing profile. Account credentials, model defaults and conversation files are preserved. Profile backups are saved under `$DSH_HOME/linkmind-install-backups`. The default home for this community desktop is `~/.local/share/dsh-linux/home`; use `--home /path/to/DSH_HOME` and `--dsh /path/to/dsh` for another installation. The checkout remains a runtime dependency; keep it at the configured path.

Reopen **DeepSeek Harness** from the application menu. Select **具身模式 · LinkMind** in a new conversation. No browser needs to be opened, and the service starts and stops with the desktop host.

## Work in the normal conversation

1. Select a model using DSH’s usual model menu. The desktop plugin uses the existing provider and login. Describe a task and request execution, for example: “启动一个 Push-T 仿真，使用最简配置。先观察场景，告诉我准备怎么做。”
2. Read streamed responses and native tool calls in the conversation. LinkMind exposes task creation, episode startup, context, available robot tools, robot calls, finish and stop through MCP. Task-specific observation, measurement and bounded action tools retain their native schemas and image results.
3. Click **运行与摄像头** in the conversation header. Switch between head, left wrist and right wrist images. The panel follows this conversation’s latest attempt or a selected earlier run, shows the control step and frame age, and keeps the last frame when a connection drops.
4. During execution, type in the same composer. Use DSH’s **插话发送** control for guidance at the next agent step. With the default **排队发送** setting, Enter queues a later message and Ctrl/Cmd+Enter uses the alternate sending behavior; queued messages also offer **插话发送**. These behaviors follow DSH’s own busy-send setting. LinkMind does not replace these controls. An already dispatched action segment finishes before new guidance can affect subsequent actions.
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

The installed `0.2.3` bundle was checked with the desktop host, and the account file remained byte-identical. A native `dsh-app` transport smoke test started a real Push-T simulation, received startup/ready/stopping/stopped events over the streaming response, loaded all three camera images, and stopped with no active simulation left. This also covers the desktop forwarding of streamed POST bodies.

In an isolated DSH profile, a real conversation streamed assistant progress and native tool calls. While it was running, **插话发送** changed the request from preparing a hold to observation only; the same turn acknowledged the change and reported control step 0 without executing actions. Camera selection and stop were exercised in the rendered UI, with light/dark themes and wide/narrow layouts inspected. The optional Codex adapter stays registered for the lifetime of its host.

The rendered interaction checks used the same client in the authenticated local Web preview. The installed Electron window itself was not driven by UI automation; its actual host/protocol and simulation lifecycle were verified separately. These are development checks, not new benchmark results.

## Project workflow verification — 0.3.0

The final pass ran 40 checks (28 Python and 12 Node), including real project subprocesses, incremental logs, source changes, original result comparison, repeat-request receipts, missing prerequisites, output path containment, detached child cleanup, timeout and owner loss. Reinstalling preserves the optional Codex setting and existing runtime options.

A real Codex conversation in the authenticated preview read an integration repository, created a Git branch, edited its launch recipe through native DSH tools and launched the original program. Changing synthetic frames, streamed logs, historical selection and the stop button were inspected in light/dark themes and 1280/900-pixel windows. The first modification attempt used a host `/tmp` directory hidden from the native shell's isolated temporary mount; it was retained, then repeated successfully inside the selected workspace. The Codex adapter now distinguishes its transport-only local sandbox from DSH's host tool permissions.

The installed `0.3.0` bundle was separately checked through the actual `dsh-app` authenticated protocol: a new project run streamed states, produced three distinct images and returned its original eight-frame JSON result. Credentials remained byte-identical and the Codex provider stayed available after restart. No Electron-window UI automation or third-party policy benchmark reproduction is claimed.

## Source

- `studio/install-desktop.mjs`: DSH bundle installation and profile preservation.
- `studio/plugin/desktop-host.mjs`, `runtime.mjs`: plugin configuration, service lifetime and mode registration.
- `studio/plugin/client.js`: run header button and native sidebar for cameras, logs and results.
- `studio/plugin/preset.mjs`, `session.mjs`: embodied mode and conversation ownership.
- `src/roborag/studio/`: episode service, camera publication and MCP bridge.

DeepSeek Harness is copyright DeepSeek under its [MIT license](https://github.com/deepseek-ai/deepseek-harness/blob/main/LICENSE). The LinkMind DSH plugin carries its own MIT notice. Credentials, machine configuration and the private manuscript are not redistributed. Published experimental scores keep their original frozen implementation and protocol provenance.
