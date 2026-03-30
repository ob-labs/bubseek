# Getting started

This guide is for the normal user flow: install bubseek, run `bub`, and add contrib with standard Python dependencies.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **Git** only if one of your dependencies comes from a Git repository

## Install

From the repository root:

```bash
git clone https://github.com/ob-labs/bubseek.git
cd bubseek
uv sync
```

This installs `bubseek` together with `bub==0.3.0a1`.

## Run Bub

Use the bundled `bub` command directly:

```bash
uv run bub --help
uv run bub chat
uv run bub run ",help"
```

Configure SeekDB or OceanBase before running `bubseek`, for example with `BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://...`.

## Add contrib

Contrib packages are standard Python packages. Add them with normal dependency management. bubseek ships `bub-web-search`, `bub-tapestore-sqlalchemy`, `bubseek-schedule`, Feishu, DingTalk, WeChat, Discord, and Marimo support by default.

**Bundled channels and tools:**

- **Feishu channel**: set `BUB_FEISHU_APP_ID` / `BUB_FEISHU_APP_SECRET`, then enable it in gateway if needed.
- **DingTalk channel**: set `BUB_DINGTALK_CLIENT_ID` / `BUB_DINGTALK_CLIENT_SECRET`, then enable it in gateway if needed.
- **WeChat channel**: run `uv run bub login wechat`, then `uv run bub gateway --enable-channel wechat`.
- **Discord channel**: set `BUB_DISCORD_TOKEN`, then `uv run bub gateway --enable-channel discord`.
- **Marimo channel**: run `uv run bub gateway --enable-channel marimo`.

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
