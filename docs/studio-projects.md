# Open, run and modify embodied projects

Use **具身模式 · LinkMind** in DSH Desktop. The conversation is the project assistant:
read a repository, prepare its dependencies, edit its code and launch its original
program. The right sidebar shows actual process output, camera files and results.
The same workflow applies to LinkMind, XPolicyLab or HexaShell; the Studio does not
replace an imported method with its own controller.

## Start from a repository

You can discover and edit configurations without sending a message first:

1. Select **具身模式 · LinkMind**, then **项目与配置** beside the workspace/mode picker.
2. Expand **作为工作区打开**. Choose **默认 Studio 工作区** (normally `~/LinkMind Studio`), or browse/paste the local directory of an existing repository, such as HexaShell. It becomes a normal DSH workspace in the left sidebar; its files stay in place.
3. The panel discovers `linkmind.studio.json` in that workspace and lists its named configurations. Select one to review its original command, model/task notes and path checks. **浏览文件** opens DSH's native file explorer for README and source inspection.
4. Choose **新建配置**, **复制所选配置**, or **编辑配置文件** to edit the JSON in the sidebar. Save validates it; missing requirements block launch. Existing invalid JSON remains editable. An on-disk change by the assistant or another editor causes a conflict instead of overwriting it. Drafts survive switching sidebar tabs during the current app session.
5. **运行所选配置** launches the reviewed configuration and opens **运行与摄像头**. Alternatively, **复制会话指令** prepares a message naming the current project and configuration; paste it into the normal conversation and send it yourself.

The default workspace is created only when selected, with an empty configuration file. It does not install a robot controller. Configurations remain ordinary project files you can version in Git or edit with another editor. Runtime edits are blocked while that project is active. This sidebar edits launch JSON; DSH's file viewer is not a replacement for a full source-code IDE.

Select or add the local repository with DSH's normal **工作区** picker. For a GitHub
URL, ask the assistant to clone it into a new working directory first. Keep the
project in the selected DSH workspace. On Linux, the shell's isolated `/tmp` may
not expose host temporary repositories; use a normal workspace directory. Then say:

> 打开这个具身项目。先读 README 和环境说明，确认原始版本、模型登录方式、
> 权重和任务入口。准备一个最小运行的启动配置，说明还缺什么，再运行它。

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
