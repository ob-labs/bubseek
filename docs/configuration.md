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

If you do not want them installed by default, put them under `optional-dependencies` instead.

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
| `BUB_FEISHU_APP_ID` | Required for Feishu channel (bundled) |
| `BUB_FEISHU_APP_SECRET` | Required for Feishu channel |
| `BUB_TAPESTORE_SQLALCHEMY_URL` | SQLAlchemy tape store URL (bundled) |

## Builtin skills

Builtin skill source files live in `src/bub_skills/`. They are packaged into `bub_skills/` in the wheel, which Bub already knows how to discover. Users do not need to run a separate sync command for them.

## Advanced: downstream skill packaging

Most users can skip this section.

If you are building your own downstream Bub distribution and want to vendor remote skill repositories at build time, use `pdm-build-bub`:

```toml
[build-system]
requires = ["pdm-backend", "pdm-build-bub==0.1.0a1"]
build-backend = "pdm.backend"

[tool.bub]
skills = [
    { git = "PsiACE/skills", include = ["python-*"] },
    { git = "https://github.com/example/skills.git", ref = "v1.2.3", subpath = "skills/review" },
]
```
