# Bubseek Agent Instructions

## Chat channels (`$dingtalk`, `$wechat`, `$feishu`, `$discord`, `$telegram`)

When the message context includes a **channel tag** (e.g. `$dingtalk`, `$wechat`, `$feishu`, `$discord`) and session/chat metadata, you are on an inbound chat channel.

- **Reply with plain text.** The framework delivers it to the user. Do not run shell commands or scripts just to answer the user.
- **Channel-specific send tools** (names vary by plugin: e.g. `dingtalk_send`, `wechat`, Discord/Feishu helpers): use them only when you must send a message **from inside another tool** (e.g. progress during a long task), not for normal turn replies.

## Marimo (`$marimo`)

Same rule: **plain text** replies go to the gateway UI.

**Data insights and charts:** write marimo `.py` notebooks under `{workspace}/insights/`. Use `@app.cell`, PEP 723, and **marimo-notebook** conventions. **Combine with other marimo skills** when useful: **anywidget**, **add-molab-badge**, **implement-paper**, **marimo-batch**, **wasm-compatibility**. The index auto-reloads when you respond.