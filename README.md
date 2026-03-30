# bubseek

[![PyPI version](https://img.shields.io/pypi/v/bubseek.svg)](https://pypi.org/project/bubseek/)
[![License](https://img.shields.io/github/license/ob-labs/bubseek.svg)](LICENSE)
[![CI](https://github.com/ob-labs/bubseek/actions/workflows/main.yml/badge.svg?branch=main)](https://github.com/ob-labs/bubseek/actions/workflows/main.yml?query=branch%3Amain)

**Enterprise-oriented distribution of [Bub](https://github.com/bubbuild/bub)** for agent-driven insight workflows in cloud-edge environments.

bubseek turns fragmented data across operational systems, repositories, and agent runtime traces into **explainable, actionable, and shareable insights** without heavy ETL. It keeps the Bub runtime and extension model while packaging a practical default distribution for real deployments.

`bubseek` packages a practical Bub distribution with SeekDB/OceanBase defaults, bundled channels, and builtin skills, without adding a second CLI surface on top of `bub`.

## Features

- **Lightweight and on-demand** — Trigger analysis when needed instead of maintaining large offline pipelines.
- **Explainability first** — Conclusions are returned together with agent reasoning context.
- **Cloud-edge ready** — Supports distributed deployment and local execution boundaries.
- **Agent observability** — Treats agent behavior as governed, inspectable runtime data.
- **Bub-compatible** — Uses Bub directly as the runtime and command surface; no fork of the core runtime.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (recommended) or pip, and Python 3.12+.

```bash
git clone https://github.com/ob-labs/bubseek.git
cd bubseek
uv sync
uv run bub --help
uv run bub chat
```

Configure SeekDB or OceanBase before running `bubseek`, using `BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://...`.

## Add contrib

Contrib packages remain standard Python packages. Add them as normal dependencies. bubseek ships its built-in channels and marimo support by default, and resolves bundled contrib packages from GitHub-hosted `bub-contrib` packages instead of local workspace packages.

```toml
[project]
dependencies = [
    "bub==0.3.0a1",
    "bub-codex @ git+https://github.com/bubbuild/bub-contrib.git@main#subdirectory=packages/bub-codex",
]
```

Then sync your environment:

```bash
uv sync
```

## Documentation

## Development

```bash
make install
make check
make test
make docs
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

[Apache-2.0](LICENSE).
