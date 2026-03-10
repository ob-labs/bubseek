# Getting started

This guide is for the normal user flow: install bubseek, run Bub through the wrapper, and add contrib with standard Python dependencies.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **Git** only if one of your dependencies comes from a Git repository

## Install

From the repository root:

```bash
git clone https://github.com/psiace/bubseek.git
cd bubseek
uv sync
```

This installs `bubseek` together with `bub==0.3.0a1`.

## Run Bub

Use `bubseek` exactly as you would use `bub`:

```bash
uv run bubseek --help
uv run bubseek chat
uv run bubseek run ",help"
```

## Use `.env`

If `.env` contains runtime credentials, bubseek forwards them to the Bub subprocess as-is:

```dotenv
BUB_MODEL=openrouter:qwen/qwen3-coder-next
BUB_API_KEY=sk-or-v1-...
BUB_API_BASE=https://openrouter.ai/api/v1
```

## Add contrib

Contrib packages are standard Python packages. Add them with normal dependency management. bubseek ships `bub-web-search`, `bub-tapestore-sqlalchemy`, and `bubseek-schedule` by default.

**Optional extras:**

- **Feishu channel**: `uv sync --extra feishu` or `pip install bubseek[feishu]`

**Add other contrib from Git:**

```toml
[project]
dependencies = [
    "bub==0.3.0a1",
    "bub-codex @ git+https://github.com/bubbuild/bub-contrib.git@main#subdirectory=packages/bub-codex",
]
```

Then refresh the environment:

```bash
uv sync
```

## Builtin skills

bubseek already ships its builtin skills in the wheel. For normal use, there is no separate skill sync step.

## Next steps

- [Configuration](configuration.md) — Common `pyproject.toml` patterns.
- [Architecture](architecture.md) — Design boundaries and responsibility split.
