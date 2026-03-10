# bubseek

[![PyPI version](https://img.shields.io/pypi/v/bubseek.svg)](https://pypi.org/project/bubseek/)
[![License](https://img.shields.io/github/license/psiace/bubseek.svg)](LICENSE)
[![CI](https://github.com/psiace/bubseek/actions/workflows/main.yml/badge.svg?branch=main)](https://github.com/psiace/bubseek/actions/workflows/main.yml?query=branch%3Amain)

**Enterprise-oriented distribution of [Bub](https://github.com/bubbuild/bub)** for agent-driven insight workflows in cloud-edge environments.

bubseek turns fragmented data across operational systems, repositories, and agent runtime traces into **explainable, actionable, and shareable insights** without heavy ETL. It keeps the Bub runtime and extension model while packaging a practical default distribution for real deployments.

## Features

- **Lightweight and on-demand** — Trigger analysis when needed instead of maintaining large offline pipelines.
- **Explainability first** — Conclusions are returned together with agent reasoning context.
- **Cloud-edge ready** — Supports distributed deployment and local execution boundaries.
- **Agent observability** — Treats agent behavior as governed, inspectable runtime data.
- **Bub-compatible** — Forwards Bub commands directly; no fork of the core runtime.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (recommended) or pip, and Python 3.12+.

```bash
git clone https://github.com/psiace/bubseek.git
cd bubseek
uv sync
uv run bubseek --help
uv run bubseek chat
```

If your runtime reads credentials from `.env`, bubseek forwards them to the Bub subprocess:

```dotenv
BUB_MODEL=openrouter:qwen/qwen3-coder-next
BUB_API_KEY=sk-or-v1-...
BUB_API_BASE=https://openrouter.ai/api/v1
```

## Add contrib

Contrib packages remain standard Python packages. Add them as normal dependencies.

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

- Optional extras: Feishu `uv sync --extra feishu`, DingTalk `uv sync --extra dingtalk`.

## Documentation

User documentation lives at:

https://psiace.github.io/bubseek/

## Development

```bash
make install
make check
make test
make docs
```

Bundled skills (friendly-python, piglet) are included when building a wheel. For editable installs (`uv sync`), use non-editable to get them: `uv pip install .` after `uv sync`, or `uv build && uv pip install dist/*.whl`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

[Apache-2.0](LICENSE).
