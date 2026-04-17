# bubseek

[![License](https://img.shields.io/github/license/ob-labs/bubseek.svg)](LICENSE)
[![CI](https://github.com/ob-labs/bubseek/actions/workflows/main.yml/badge.svg?branch=main)](https://github.com/ob-labs/bubseek/actions/workflows/main.yml?query=branch%3Amain)

A Bub distribution for data-driven insight workflows, powered by [OceanBase seekdb](https://github.com/oceanbase/seekdb).

## What is bubseek

bubseek packages [Bub](https://github.com/bubbuild/bub) with ready-to-use components for rapid data consumption. It's an attempt to explore a different approach to enterprise data needs: instead of scheduling BI tickets, tell the agent what you want and get insights back.

**Multi-channel entry** — Feishu, DingTalk, WeChat, WeCom, Discord, Telegram, and a built-in marimo web interface. Configure env vars and enable via gateway.

**Lightweight data consumption** — marimo notebooks for dashboards, github-repo-cards for generating shareable repo cards, schedule tasks with cron support. Add insights to `insights/` and the agent can work with them dynamically.

**Built-in observability** — Tape records everything (conversations, reasoning, tool calls), stored in seekdb, viewable via marimo dashboard. The agent's own footprint becomes data that can be queried and analyzed.

**Unified data substrate** — All data (tapes, sessions, tasks) flows into a single seekdb instance. One database, three data types. If you outgrow seekdb, migrate seamlessly to full OceanBase.

## Quick Start

```bash
git clone https://github.com/ob-labs/bubseek.git
cd bubseek
uv sync
uv run bub --help
```

Configure model and database, then verify:

```bash
export BUB_MODEL=openrouter:qwen/qwen3-coder-next
export BUB_API_KEY=sk-or-v1-your-key
export BUB_API_BASE=https://openrouter.ai/api/v1
export BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://user:pass@host:port/database
uv run bub chat
```

See [Getting started](docs/getting-started.md) for detailed setup guide.

## License

[Apache-2.0](LICENSE)
