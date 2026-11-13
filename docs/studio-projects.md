# Open, run and modify embodied projects

Use **具身模式 · LinkMind** in DSH Desktop. The conversation is the project assistant:
read a repository, prepare its dependencies, edit its code and launch its original
program. The right sidebar shows actual process output, camera files and results.
The same workflow applies to LinkMind, XPolicyLab or HexaShell; the Studio does not
replace an imported method with its own controller.

## Start from a repository

Select the repository with DSH's normal **工作区** picker and choose **具身模式 · LinkMind**. Type `/` in the conversation and choose **goal**, then describe the outcome:

```text
/goal 复现 当前仓库的 Push-T，保留原模型、场景和预算，运行并核对原始结果。
```

Use ordinary messages for guidance or a one-off run. Choose one of three native Goal extensions: `/goal reproduce <request>`, `/goal optimize <request>` or `/goal develop <request>` (Chinese 复现/优化/开发 also work). The assistant refines the supplied instruction into a task brief and useful steps; the user does not fill a work hierarchy or acceptance form. A launch recipe is needed only for managed execution; the assistant can prepare it from the original README and entry point.

`/goal` shows the current native goal; `/goal edit <objective>` changes it; `/goal pause`, `/goal resume` and `/goal clear` control its lifecycle. Pausing continuation does **not** stop an external process; use **运行与摄像头 → 停止运行** for that. Goals are session-scoped and need rearming after a host restart or session fork. DSH's native round limits apply.

To inspect configurations manually, open the native file sidebar and click **运行配置**, or add that tab from the right sidebar. It lists `linkmind.studio.json` recipes, their command/model notes and path checks. New, copy and JSON editing remain optional; saving validates the file and concurrent edits cause a conflict. You can run a configuration directly or copy a launch instruction into the conversation. No project-goal association is required.

For a GitHub URL, ask the assistant to clone into a working directory first. Environment setup still follows the repository instructions. On Linux use a normal workspace directory, since the shell's isolated `/tmp` may not expose host temporary repositories.

The assistant uses native DSH file, search and shell tools. It registers the local
path using `open_project`. That operation only inspects the project; it does not
install dependencies or execute a repository's setup scripts. Environment setup
uses the repository's instructions and DSH's normal permissions. Reuse a known
working environment when appropriate, and use a separate environment for projects
with conflicting requirements.

There is no universal one-click reproduction of arbitrary repositories. A method
may require simulator assets, downloaded checkpoints, a GPU, API access or a
particular version. The assistant should report missing prerequisites explicitly.
Names such as “GPT-6-Astra” alone do not specify an experimental protocol.

## Conversation model and tested model

Choose the **assistant** in DSH's normal model picker, including the optional local
Codex provider. This model helps read, run and modify projects.

The **tested policy/model** belongs to the original program's arguments and
configuration. For an existing XPolicyLab or HexaShell method, preserve its model,
authentication route, prompt, controller, environment and budget. Selecting GPT
in the conversation does not automatically switch that program's model or give
it Codex authentication. Record the actual settings in recipe metadata and verify
them against the original program's configuration/output.

For LinkMind's separate built-in interactive simulation, the conversation model
itself operates the episode tools. That route still supports native **插话发送**
between action segments.

## A saved launch recipe

Keep `linkmind.studio.json` at the opened project root. For example, **after checking
the repository's real CLI**:

```json
{
  "version": 1,
  "recipes": {
    "original": {
      "argv": ["{project}/.venv/bin/python", "run.py", "--output", "{output}"],
      "cwd": ".",
      "checks": [
        {"kind": "path", "value": "weights/policy.pt", "label": "Policy weights"}
      ],
      "timeout_seconds": 5400,
      "result": "result.json",
      "cameras": {"head": "live/head.png"},
      "metadata": {
        "method": "original implementation",
        "model": "model actually configured in the project",
        "task": "task and scene identifier",
        "seed": 1
      }
    }
  }
}
```

`argv` is an argument array, not a shell command. Use the real interpreter path;
DSH does not activate a project's virtual environment automatically. `{project}`
and `{output}` expand to absolute paths. Every run receives a new output path,
which the original runner creates. The same path is supplied as
`LINKMIND_RUN_OUTPUT`. Do not reuse a frozen experiment's output directory.

`cwd` must stay inside the project. `checks` can verify `path` or `executable`
requirements, but do not establish that dependencies are compatible. Non-secret
`env` values may be set; credentials stay in the existing provider environment or
its local login store. The service's private token and injected Python path are
removed from the child environment. Project execution uses the local user's
permissions; it is not a container or an isolation boundary.

`result` and `cameras` are optional paths relative to that run's output. The sidebar
supports up to eight PNG/JPEG/WebP image files. The program should atomically
replace them. An upstream project without a camera export needs a small adapter;
the Studio does not invent a live feed or automatically decode arbitrary video,
ROS topics or a remote camera. Results are shown as original JSON up to 128 KiB;
other/large reports remain in the output directory.

## Run, observe and change

Ask “运行 original 配置”. The assistant calls `run_project` with a unique request
identity. Reusing that identity returns the existing receipt, including after a
lost response. An intentional rerun requires a new identity.

Open **运行与摄像头**. Logs stream independently of model replies, so the program
continues after the assistant has finished its turn. Select a previous run to
inspect it, or leave **跟随最新运行** selected. The panel keeps the latest 32 KiB of
text; the complete `runner.log` is preserved. **停止运行** terminates the program and
its owned descendants, retaining incomplete output. Closing the desktop also
stops owned runs. One managed project or simulation runs at a time.

Use the same conversation to ask for explanations or changes:

> 先保留这次原版运行。停止当前程序，在新分支里修改动作步长，另存 modified
> 配置后再跑一次，对比两次的原始结果、模型、预算和代码差异。

The assistant edits with DSH's normal code tools. Stop a running project before
editing code it may still read. Ordinary chat guidance is sent to the development
assistant; it does not alter an external policy mid-run. Runtime steering needs
that project's own explicit interface. The built-in interactive LinkMind route
continues to support conversational steering as before.

Each run stores the exact recipe/argv, original Git HEAD, tracked diff, hashes of
non-ignored untracked files, log, exit status and original outputs under
`$DSH_HOME/linkmind/project-runs/<id>`. Ignored assets, full dependencies, secrets
and untracked file contents are not archived, so these records are **provenance,
not a complete reproducibility package**. Metadata is user/project supplied.
`compare_project_runs` returns two raw records and changed fields, not a derived
benchmark score. A clean process exit does not establish task success.

## Try the workflow without a simulator

[The integration example](../examples/studio-project) uses Python's standard
library and takes about eight seconds. Say:

> 打开 LinkMind 仓库里的 examples/studio-project，运行 smoke 配置。

It emits moving synthetic frames, incremental text and JSON. To try modification
and comparison, ask the assistant to copy the example into a new Git repository,
run the original, change `--steps` in a second recipe, and compare the two records.
This is a Studio integration check, not an embodied benchmark or a reproduction
of XPolicyLab, LinkMind or HexaShell results.

## Shared tasks and native Goal

The **任务** panel shows the original request, refined brief, constraints, verification criteria, work progress, decisions, evidence and linked runs. New tasks start without fabricated criteria or a fixed checklist. The assistant maintains them with `update_project` operations `refine_task`, `save_work` and `save_record`; optimistic revisions prevent overwriting another writer.

The shared task belongs to its canonical workspace. Native Goal owns continuation in the current conversation. In another conversation in the same workspace, choose the task and click **在此会话接续**, or use `/goal tasks` then `/goal continue <id>`. Original instructions, refinements and evidence stay with the same task, and the new conversation receives them as context. Task type remains reproduction, optimization or development.

Only one conversation owns execution. Transfer refuses while the previous conversation is running; pause it and wait for the current turn to settle first. An idle previous Goal is paused on transfer. Stale native events and old-conversation writes cannot overwrite the new owner. An existing unfinished Goal in the destination must first be cleared. `/goal clear` detaches without deleting the shared task. Completing native Goal is shown as assistant-reported completion, not independent benchmark certification.

Managed runs automatically associate with the current active shared task; explicit legacy associations still work. Original recipes and results remain the source for experimental claims. The panel links the run to its camera and logs.

Task data persists in `project-book.sqlite3`; DSH owns durable conversation/Goal history. Host exit stops execution and rearming is explicit after restart. There is no cross-device synchronization or background daemon. The old 0.5.0 project forms are removed, but their historical records, evidence and revisions remain queryable; they are not silently converted into native Goals. Back up the plugin state while DSH is stopped.
