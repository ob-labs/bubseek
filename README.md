# bubseek

[![License](https://img.shields.io/github/license/ob-labs/bubseek.svg)](LICENSE)
[![CI](https://github.com/ob-labs/bubseek/actions/workflows/main.yml/badge.svg?branch=main)](https://github.com/ob-labs/bubseek/actions/workflows/main.yml?query=branch%3Amain)

A database-native Agent Harness, by the [OceanBase](https://en.oceanbase.com/) OSS Team.

## What is bubseek

bubseek is a [Bub](https://github.com/bubbuild/bub) distribution for teams that want a unified data substrate for agents.

It follows the same open standards around [agents.md](https://agents.md/) and [Agent Skills](https://agentskills.io/), while treating the database as the natural place to keep agent context, execution history, and observability together. The same data can then serve operational visibility, testing, trajectory comparison, and training workflows without being copied into separate systems or re-ingested later. A related view is reflected in [Tape](https://tape.systems/).

## Why bubseek

- **Built on the same open agent standards** — Use `AGENTS.md` and Agent Skills as first-class parts of the authoring and extension model.
- **Context and observability in one substrate** — Conversations, tool spans, tasks, and execution history live in the same database, so the agent's runtime footprint is queryable by default.
- **Multi-channel by design** — Run the same agent across Feishu, DingTalk, WeChat, WeCom, Discord, Telegram through one harness.
- **Database-native operations** — Reuse database permissions, SQL queries, and operational tooling rather than building a parallel file and logging stack.
- **From local to cloud** — Run on a database-backed deployment path from day one. When you want one product line from local development to distributed production, [OceanBase seekdb](https://github.com/oceanbase/seekdb) and OceanBase are the recommended option.
- **No secondary ingestion** — Once traces are stored in the database, they are ready for analysis, trajectory comparison, eval workflows, or training pipelines without re-importing the same data elsewhere.

## What ships in the harness

- **Database-native runtime** — bubseek packages Bub around database-backed tape storage instead of a file-heavy context stack, with OceanBase offered as a recommended local-to-cloud solution.
- **Inbound channels** — Gateway integrations for chat platforms let the same harness serve users across different operational surfaces.
- **Pythonic development and extension workflow** — Use packaged skills for Python development and plugin creation, then extend the harness with contrib packages as ordinary Python dependencies.
- **Queryable agent footprint** — Tape-backed sessions, tasks, and traces can be inspected directly in the database and reused by downstream analysis workflows.

## What this architecture unlocks

- Keep agent context and observability together instead of maintaining separate operational systems.
- Let database access control and query capabilities apply directly to agent runtime data.
- Move from local experiments to larger deployments without redesigning the storage model.
- Turn production traces into reusable data assets for offline analysis and model improvement.

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

## Learn more

- [Getting started](docs/getting-started.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)

## License

[Apache-2.0](LICENSE)
