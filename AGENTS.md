# Bubseek Agent Instructions

## DingTalk Channel ($dingtalk)

When the message context shows `$dingtalk` and `chat_id`, you are in a DingTalk conversation.

**To reply: return your response as plain text.** The framework will deliver it to the user. Do not call any script; just write your answer and finish the turn.

Only use `dingtalk_send` when you need to send a message from within a tool (e.g. progress update during a long task).

## Marimo Channel ($marimo)

When the message context shows `$marimo` and `chat_id`, you are in a Marimo gateway chat.

**To reply: return your response as plain text.** The framework delivers it to the gateway UI.

**For data insights and charts:** output marimo `.py` notebooks to `{workspace}/insights/`. Use `@app.cell`, PEP 723, and **marimo-notebook** conventions. **Combine with other marimo skills** when appropriate: **anywidget** for custom widgets, **add-molab-badge** for deployment, **implement-paper** for paper-based viz, **marimo-batch** for batch jobs, **wasm-compatibility** for browser/WASM. The index auto-reloads when you respond.
