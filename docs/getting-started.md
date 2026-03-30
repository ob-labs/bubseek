# Getting started

bubseek is an attempt to explore a different approach to enterprise data needs: instead of scheduling BI tickets, tell the agent what you want and get insights back.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip

## Install

```bash
git clone https://github.com/ob-labs/bubseek.git
cd bubseek
uv sync
```

## Run

```bash
uv run bub --help
uv run bub chat
```

## Configure database

Set `BUB_TAPESTORE_SQLALCHEMY_URL` before running:

```bash
export BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://user:pass@host:port/database
```

## Enable channels

Configure environment variables, then enable via gateway:

| Channel | Environment Variables |
| --- | --- |
| Feishu | `BUB_FEISHU_APP_ID`, `BUB_FEISHU_APP_SECRET` |
| DingTalk | `BUB_DINGTALK_CLIENT_ID`, `BUB_DINGTALK_CLIENT_SECRET` |
| Discord | `BUB_DISCORD_TOKEN` |
| Telegram | `BUB_TELEGRAM_TOKEN` (built-in via bub) |
| Marimo | `uv run bub gateway --enable-channel marimo` |

WeChat: run `uv run bub login wechat` first.

## What you can do

- **Data consumption** — Tell the agent what insight you want, it works with marimo notebooks in `insights/`
- **Observability** — All agent interactions are stored as tapes in seekdb, viewable via marimo dashboard
- **Scheduling** — Create cron-style tasks: "remind me to check data every morning"

## Next steps

- [Configuration](configuration.md) — Channel credentials, skills, runtime options
- [Architecture](architecture.md) — Design overview