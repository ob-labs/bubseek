# Development

This page covers local development for the bubseek repository.

## Setup

From the repository root:

```bash
uv sync
make install
```

`make install` creates the virtual environment, installs dependencies, and installs pre-commit hooks.

## Common commands

| Command | Description |
| --- | --- |
| `make install` | Install dependencies and pre-commit hooks. |
| `make check` | Run lock verification, linting, formatting checks, and type checks. |
| `make test` | Run pytest. |
| `make build` | Build the wheel and source distribution. |
| `make docs` | Serve documentation locally. |
| `make docs-test` | Build documentation and fail on warnings. |

## Testing

```bash
make test
```

Or directly:

```bash
uv run pytest tests
```

## Building

```bash
make build
```

The wheel includes builtin skills from `bub_skills/`.
The source files for those builtin skills live in `src/bub_skills/`.

## Docs

```bash
make docs
make docs-test
```

## Contributing

See [CONTRIBUTING.md](https://github.com/ob-labs/bubseek/blob/main/CONTRIBUTING.md).
