# Learning from DeepSeek SuperAgent

Reference: [dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype), reviewed at `8c32a9dc5d72c033816c6a8110b37f40cf94fba4` on 2026-11-12. This is DeepSeek's published research prototype; its README distinguishes it from an official product and from designs discussed but not implemented in the accompanying article. No SuperAgent code is included here.

## What transfers to LinkMind

SuperAgent's [philosophy](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/000-philosophy.md) treats human attention as a cost. Its panel prioritizes decisions and problems. LinkMind should make the requested outcome, current progress and an actionable stop visible, while detailed telemetry remains inspectable in the native conversation trajectory. The user should not need to learn the infrastructure taxonomy to use the product.

Its [domain model](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/001-domain.md) separates a work item from an assignment to an executor. LinkMind needs the same distinction: a continuing user goal can survive many robot attempts and model upgrades. A simulation reset ends an attempt, not the user's relationship with the task. Each attempt must retain its scene, model, support version and actual result.

Its [execution path](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/003-execution.md) delivers follow-up input to an existing executor. Short foreground waits let it receive new input at step boundaries. In LinkMind, a correction should reach the ongoing task through its conversation. It must not create an unrelated task or live in a separate "leave a clue" form. Already executing physical actions are a separate concern: guidance applies before subsequent actions; stopping the simulator has its own explicit control.

Its [prompt versioning](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/004-prompts.md) records immutable revisions and which revisions sessions used. LinkMind can use that idea for requirements and experience proposals. "The agent saved a suggestion" and "a candidate improved outcomes on matched evaluation scenes" must remain distinguishable.

## Product direction

The primary surface is a conversation with an embodied agent. Goals, clarifications, observations, action summaries, corrections and outcomes belong there. A side panel shows the current scene. Historical experiences are source-linked references available to both the person and the agent. A reference describes what happened under particular conditions, including uncertainty and failure; a skill supplies reusable operating instructions. The two must not be conflated. Selection may borrow the convenience of a skill picker, but adds a reference to the current conversation and never compels a fixed stage sequence.

A persistent coordinating conversation may eventually delegate concrete attempts to execution sessions. That separation should appear only when it improves responsiveness, continuity or isolation. A simple task should not pay for a compulsory router, planner, executor and evaluator chain. The current preview deliberately uses dsh's ordinary agent loop and a single simulation service; it does not implement SuperAgent's router/worker system.

## What must change for embodiment

Software worker concurrency does not authorize concurrent commands to one robot. A future session-assignment layer needs an exclusive robot lease, recorded command receipts, observation freshness and clear transfer of control. Re-delivering a message can be deduplicated by ID; repeating an uncertain physical action can still be harmful. After a crash, restore the conversation and verify the scene before deciding whether anything can continue. Never equate transcript recovery with physical-state recovery.

Background silence is appropriate for routine computation, but the person must still be able to inspect ongoing action and intervene. The UI should show progress continuously without generating a new notification for every tool call. Operational stopping must remain independent of model reasoning.

## RSI and infrastructure half-life

A useful improvement loop has four steps: retain an attributed failure or costly success, propose a change, evaluate the candidate against a fixed baseline, and adopt a version only when the evidence supports it. The proposal may remove a redundant tool, shorten an experience, or change when retrieval is offered. Execution does not silently alter the mechanism judging it.

The persistent needs layer does not prove immunity to infrastructure half-life. It moves the stable contract toward user intent and lets capability-dependent support be replaceable. The testable claim is narrower: **can selecting less or different support preserve task satisfaction while reducing overhead as model capability and task difficulty change?**

Measure task completion, native score, violations of user constraints, intervention count, runtime and model/tool cost. Compare a minimal interface, fixed full support and a candidate selector on the same task/model/scene budgets. Easy Push-T findings motivate that comparison; they do not establish it for harder tasks or a universal decay law.

Implemented in this preview: native conversation and next-step steering, shared experience references, persistent tasks, host-attributed conversation assignments, separate attempt records and serialized simulator calls. Proposed: an evaluated selector and versioned promotion of infrastructure changes.
