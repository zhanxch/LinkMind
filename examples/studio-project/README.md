# Studio integration check

This small standalone program verifies project launch, incremental logs, changing
PNG frames and original JSON results. It uses only Python's standard library.
Its blue dot is synthetic; it does not measure an embodied policy or call a model.

Open this directory in a **具身模式 · LinkMind** conversation and ask to run the
`smoke` recipe in `linkmind.studio.json`. Open **运行与摄像头** to see output.
Ask the assistant to copy this example into a new local Git repository before
editing it if you want to try the original → modify → compare workflow.

The application supplies a new `LINKMIND_RUN_OUTPUT` path for every run. This
example creates it and atomically replaces `frame.png` so readers never see a
partially written image. Your real project can instead use its own CLI argument
with `{output}`. See [project workflow](../../docs/studio-projects.md).
