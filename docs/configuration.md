# Configuration

## Philosophy

bubseek explores a different approach: instead of scheduling BI tickets, tell the agent what you want and get insights back. All agent interactions are stored as tapes in seekdb, creating a feedback loop where the agent can analyze its own footprint.

## Environment variables

### Model (required)

See [Getting started](getting-started.md) for model configuration.

### Database (required for tape storage)

See [Getting started](getting-started.md) for database configuration.

## Channels

### Feishu

1. Visit [https://open.feishu.cn/app](https://open.feishu.cn/app) → Create or select app
2. Go to "Credentials & Basic Info" → Get App ID and App Secret
3. Configure event subscriptions and permissions as needed

```bash
export BUB_FEISHU_APP_ID=cli_xxx
export BUB_FEISHU_APP_SECRET=xxx
uv run bub gateway --enable-channel feishu
```

### DingTalk

1. Visit [https://open-dev.dingtalk.com/](https://open-dev.dingtalk.com/) → Create or select app
2. Go to app details → Get Client ID and Client Secret

```bash
export BUB_DINGTALK_CLIENT_ID=xxx
export BUB_DINGTALK_CLIENT_SECRET=xxx
uv run bub gateway --enable-channel dingtalk
```

### Discord

1. Visit [https://discord.com/developers/applications](https://discord.com/developers/applications) → New Application
2. Go to "Bot" → Add Bot
3. Click "Reset Token" to get bot token
4. Enable "Message Content Intent" in Bot settings

```bash
export BUB_DISCORD_TOKEN=your-bot-token
uv run bub gateway --enable-channel discord
```

### Telegram

1. Open Telegram, search @BotFather
2. Send `/newbot` and follow instructions
3. BotFather returns the token

```bash
export BUB_TELEGRAM_TOKEN=your-bot-token
uv run bub gateway --enable-channel telegram
```

### WeChat

Interactive login required:

```bash
uv run bub login wechat    # Scan QR code with WeChat app
uv run bub gateway --enable-channel wechat
```

### WeCom

1. Visit WeCom AI bot admin console and create or select a bot
2. Enable long-connection mode, then get Bot ID and Secret
3. If needed, configure direct-message or group allowlist policies

```bash
export BUB_WECOM_BOT_ID=your-bot-id
export BUB_WECOM_SECRET=your-long-connection-secret
# optional
# export BUB_WECOM_WEBSOCKET_URL=wss://openws.work.weixin.qq.com
# export BUB_WECOM_DM_POLICY=open
# export BUB_WECOM_ALLOW_FROM='["alice", "bob"]'
# export BUB_WECOM_GROUP_POLICY=open
# export BUB_WECOM_GROUP_ALLOW_FROM='["wrXXX", "wrYYY"]'
uv run bub gateway --enable-channel wecom
```

### Marimo (web dashboard)

```bash
export BUB_MARIMO_HOST=127.0.0.1  # optional
export BUB_MARIMO_PORT=2718       # optional
uv run bub gateway --enable-channel marimo
```

Visit http://127.0.0.1:2718 after enabling.

## Other settings

| Variable | Description |
| --- | --- |
| `BUB_HOME` | Data directory (default: `~/.bub`) |
| `BUB_MAX_STEPS` | Max steps per conversation |
| `BUB_MAX_TOKENS` | Max tokens per response |
| `BUB_SEARCH_OLLAMA_API_KEY` | For web search tool |

## Add contrib packages

Treat contrib as ordinary Python packages:

```toml
[project]
dependencies = [
    "bub-codex @ git+https://github.com/bubbuild/bub-contrib.git@main#subdirectory=packages/bub-codex",
]
```

Then run `uv sync`.

## Builtin skills

Skills are packaged in the wheel. No extra sync step needed.

- `github-repo-cards` — generate repo summary cards
- `web-search` — search the web
- `schedule` — cron-style task scheduling
- `friendly-python`, `piglet` — from PsiACE/skills
- `plugin-creator` — from bub-contrib

## Marimo dashboard

Run `uv run bub gateway --enable-channel marimo`, then visit http://127.0.0.1:2718

Notebooks are generated to `insights/` at runtime. The dashboard shows agent's own footprint — tapes, sessions, task history — enabling the agent to analyze itself.
