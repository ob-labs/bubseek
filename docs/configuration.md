# Configuration

bubseek uses standard Python packaging metadata from `pyproject.toml`.

Most users only need to care about two things:

1. which Bub version is pinned
2. which contrib packages are installed

## Pin Bub

Pin Bub like a normal dependency:

```toml
[project]
dependencies = [
    "bub==0.3.0a1",
]
```

## Add contrib packages

Treat contrib as ordinary Python packages. For Git-hosted contrib packages, use direct references:

```toml
[project]
dependencies = [
    "bub==0.3.0a1",
    "bub-codex @ git+https://github.com/bubbuild/bub-contrib.git@main#subdirectory=packages/bub-codex",
]
```

If you do not want them installed by default, put them under `optional-dependencies` instead:

```toml
[project.optional-dependencies]
feishu = ["bub-feishu"]
dingtalk = ["bub-dingtalk"]
wechat = ["bub-wechat"]
marimo = ["bubseek-marimo"]
```

Install with: `uv sync --extra feishu` or `pip install bubseek[feishu]` (Feishu); `uv sync --extra dingtalk` or `pip install bubseek[dingtalk]` (DingTalk); `uv sync --extra wechat` or `pip install bubseek[wechat]` ([WeChat](https://github.com/bubbuild/bub-contrib/tree/main/packages/bub-wechat)); `uv sync --extra marimo` or `pip install bubseek[marimo]` (Marimo channel with bundled notebook skills).

## Runtime credentials

bubseek forwards `.env` values to the Bub subprocess. Bub reads `BUB_*` variables (see [Bub deployment](https://github.com/bubbuild/bub/blob/main/docs/deployment.md)).

**Minimal OpenRouter setup:**

```dotenv
BUB_MODEL=openrouter:qwen/qwen3-coder-next
BUB_API_KEY=sk-or-v1-...
BUB_API_BASE=https://openrouter.ai/api/v1
```

**Common variables:**

| Variable | Description |
| --- | --- |
| `BUB_MODEL` | Model ID (default: `openrouter:qwen/qwen3-coder-next`) |
| `BUB_API_KEY` | Provider API key |
| `BUB_API_BASE` | Provider base URL (e.g. OpenRouter) |
| `BUB_HOME` | Data directory (default: `~/.bub`) |
| `BUB_TELEGRAM_TOKEN` | Required for Telegram channel |
| `BUB_TELEGRAM_ALLOW_USERS` | Comma-separated user allowlist |
| `BUB_TELEGRAM_ALLOW_CHATS` | Comma-separated chat allowlist |
| `BUB_SEARCH_OLLAMA_API_KEY` | Required for web.search tool (bundled) |
| `BUB_SEARCH_OLLAMA_API_BASE` | Ollama API base (default: `https://ollama.com/api`) |
| `BUB_FEISHU_APP_ID` | Required for Feishu channel (optional extra: `bubseek[feishu]`) |
| `BUB_FEISHU_APP_SECRET` | Required for Feishu channel |
| `BUB_DINGTALK_CLIENT_ID` | AppKey for DingTalk channel (optional extra: `bubseek[dingtalk]`) |
| `BUB_DINGTALK_CLIENT_SECRET` | AppSecret for DingTalk channel |
| `BUB_DINGTALK_ALLOW_USERS` | Comma-separated staff_ids, or `*` for all |
| WeChat token file | After `bub login wechat`, credentials live under `~/.bub/wechat_token.json` (optional extra: `bubseek[wechat]`); see [bub-wechat](https://github.com/bubbuild/bub-contrib/tree/main/packages/bub-wechat) |
| `BUB_MARIMO_HOST` | Marimo channel bind host (default: `127.0.0.1`) |
| `BUB_MARIMO_PORT` | Marimo channel bind port (default: `2718`) |
| `BUB_MARIMO_WORKSPACE` | Workspace for insights (default: `BUB_WORKSPACE_PATH` or `.`) |
| `BUB_TAPESTORE_SQLALCHEMY_URL` | SQLAlchemy tape store URL (bundled) |

When `BUB_TAPESTORE_SQLALCHEMY_URL` is unset, bubseek builds a SeekDB/OceanBase URL from the `OCEANBASE_*` variables. Set either the full `mysql+oceanbase://...` URL or the `OCEANBASE_*` fields before running.

## Builtin skills

Builtin skill source files live in `src/skills/`. They are packaged into `skills/` in the wheel, which Bub already knows how to discover. Users do not need to run a separate sync command for them.

bubseek also vendors skills at build time via `pdm-build-skills`; these are merged into the wheel under `skills/`:

- `friendly-python` and `piglet` from [PsiACE/skills](https://github.com/PsiACE/skills)
- `plugin-creator` from [bub-contrib/.agents/skills/plugin-creator](https://github.com/bubbuild/bub-contrib/tree/main/.agents/skills/plugin-creator)

The optional `bubseek[marimo]` extra provides:
- **MarimoChannel** — inbound WebSocket for gateway; chat dashboard at `http://0.0.0.0:2718/`
- **marimo skill** — output data insights as marimo `.py` notebooks; index of charts in `{workspace}/insights/`
- References [marimo-team/skills](https://github.com/marimo-team/skills) marimo-notebook conventions

The dashboard and index are generated into `{workspace}/insights/` at runtime from one canonical template source. They should not be hand-edited inside the repository.

Run `bubseek gateway --enable-channel marimo` to enable the marimo dashboard.

## Advanced: downstream skill packaging

Most users can skip this section.

If you are building your own downstream Bub distribution and want to vendor remote skill repositories at build time, use `pdm-build-skills`:

```toml
[build-system]
requires = ["pdm-backend", "pdm-build-skills>=0.1.0a3"]
build-backend = "pdm.backend"

[tool.pdm.build]
skills = [
    { git = "PsiACE/skills", subpath = "skills", include = ["friendly-python", "piglet"] },
    { git = "https://github.com/example/skills.git", ref = "v1.2.3", subpath = "skills/review" },
]
```
