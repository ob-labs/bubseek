# Configuration

## Philosophy

bubseek explores a different approach: instead of scheduling BI tickets, tell the agent what you want and get insights back. All agent interactions are stored as tapes in seekdb, creating a feedback loop where the agent can analyze its own footprint.

## Environment variables

### Model (required)

```dotenv
BUB_MODEL=openrouter:qwen/qwen3-coder-next
BUB_API_KEY=sk-or-v1-...
BUB_API_BASE=https://openrouter.ai/api/v1
```

### Database (required for tape storage)

```dotenv
BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://user:pass@host:port/database
```

### Channels

| Channel | Environment Variables |
| --- | --- |
| Feishu | `BUB_FEISHU_APP_ID`, `BUB_FEISHU_APP_SECRET` |
| DingTalk | `BUB_DINGTALK_CLIENT_ID`, `BUB_DINGTALK_CLIENT_SECRET` |
| Discord | `BUB_DISCORD_TOKEN` |
| Telegram | `BUB_TELEGRAM_TOKEN` (built-in via bub) |
| WeChat | Run `uv run bub login wechat` first |
| Marimo | `BUB_MARIMO_HOST`, `BUB_MARIMO_PORT` |

### Other

| Variable | Description |
| --- | --- |
| `BUB_HOME` | Data directory (default: `~/.bub`) |
| `BUB_MAX_STEPS` | Max steps per conversation |
| `BUB_MAX_TOKENS` | Max tokens per response |
| `BUB_SEARCH_OLLAMA_API_KEY` | For web search tool |
| `BUB_WORKSPACE_PATH` | Workspace directory |

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