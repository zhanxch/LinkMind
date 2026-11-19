# 控制会话事件协议

Studio 直接读取控制 Agent 写出的结构化事件。程序 stdout、stderr 是诊断日志，不会被推测或改写成对话。模型不输出的内容不会被补造。

## Codex CLI

在 recipe 中指定：

```json
"conversation": {"format": "codex-jsonl", "path": "agent-events.jsonl"}
```

省略时兼容已有 HexaShell 输出：依次检查 `agent-events.jsonl` 和 `hexashell/agent-events.jsonl`。这些路径相对于本次运行的输出目录。仅支持目录内的常规文件。

支持 `thread.started`、`turn.started/completed/failed`、`item.started/updated/completed`。Agent/user message 原样显示；command execution 展示 command、aggregated_output、status、exit_code；MCP 工具展示 server/tool、arguments、result/error。`reasoning` 仅显示事件源实际提供的文本并标注摘要，不代表完整内部推理。其他 item 展示原始结构，未知顶层事件给出提示。

界面根据事件到达更新，不模拟打字。若 CLI 只在消息完成时给出文本，界面也只能在该边界更新；工具开始和完成可以分别出现。

## API / 自定义 runner

```json
"conversation": {"format": "linkmind-events", "path": "control.jsonl"}
```

由实际调用 API 的 runner 写出以下 UTF-8 JSONL 事件，每行 flush：

```jsonl
{"type":"session","thread_id":"provider-session-id"}
{"type":"message","id":"m1","role":"assistant","text":"正在观察场景","status":"in_progress"}
{"type":"message","id":"m1","role":"assistant","text":"正在观察场景，先读取相机。","status":"completed"}
{"type":"tool","id":"t1","name":"observe","arguments":{"camera":"head"},"status":"in_progress"}
{"type":"tool","id":"t1","name":"observe","arguments":{"camera":"head"},"output":{"frame":"head.png"},"status":"completed"}
```

示例只是协议说明，不是实际实验记录。`id` 在文件内稳定且唯一；同一个 id 的后续事件提供完整快照并更新原卡片，不能把不同工具重用一个 id。API 的 token delta 由 runner 累积成 text 快照再写入。工具参数和结果允许 JSON 值。`type: error` 和 `type: status` 用 `id/text` 提供真实错误及状态。

## 读取与交互

- 默认约 800 ms 追读；积压事件分页快速追上。断开后从字节游标继续，半行和半个 UTF-8 字符等待后续写完。
- 文件替换或缩短会重置游标；同一 inode 原地覆盖且长度不变不属于协议，runner 应只追加或通过替换文件开启新记录。
- 单条事件限 2 MB；超出后明确提示并暂停该处读取，不静默丢弃工具结果。每页最多 100 事件，展示最近 1500 项；完整证据仍在原文件。工具长文本默认折叠，展开可看完整返回。
- 摄像头显示最新快照；历史会话重放时不宣称画面与每条历史事件逐帧同步。
- 查看通道是只读。中途引导必须通过方案自己的输入接口实现；本版本不会把下方助手的消息悄悄注入外部 Codex 会话。
- 左侧文件夹保存在插件 state 的 `conversation-library.sqlite3`。它在原生工作区内组织会话 ID；新会话显式使用所选工作区 ID 创建，不沿用当前聊天的工作区。归类不移动代码或改变 cwd，不自动绑定 Goal。旧预览版分类按原生工作区成员迁移；无法确定归属的旧记录保留，待工作区可用后再归类。
