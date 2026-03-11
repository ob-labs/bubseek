# bubseek-marimo

Marimo channel for Bub — native marimo dashboard with chat and insights index.

## What It Provides

- **Marimo dashboard** — native marimo app: chat with Bub + insights index
- **Chat** — native marimo form widgets posting to `/api/chat`
- **Insights output** — notebooks are generated into the canonical runtime directory: `<workspace>/insights`
- **marimo skill** — output insights as `.py` notebooks; combine with marimo-team skills

## Installation

```bash
uv sync --extra marimo
# or
pip install bubseek[marimo]
```

## Gateway

```bash
bubseek gateway --enable-channel marimo
```

Open `http://localhost:2718/` — marimo gallery. Click **dashboard** for chat + index. Chat uses native marimo form widgets and posts to `/api/chat`.

## Insight Output

- Canonical runtime location: `<workspace>/insights/*.py`
- `dashboard.py`, `index.py`, and `example_visualization.py` are generated starter notebooks, not hand-maintained repository assets
- `workspace` resolution order: `BUB_MARIMO_WORKSPACE` -> `BUB_WORKSPACE_PATH` -> current working directory
- Packaged plugin installs still write generated notebooks into the active workspace, never into the installed package directory
- Format: single `.py` with `@app.cell`, PEP 723
- Gallery notebooks must contain the scanner markers `import marimo` and `marimo.App`

## Verification

```bash
# From repo root — runs E2E tests (gallery, dashboard, index, example, chat API)
./contrib/bubseek-marimo/scripts/verify_marimo.sh
# or
uv run pytest contrib/bubseek-marimo/tests/test_marimo_e2e.py -v
```

The E2E suite runs with `BUB_RUNTIME_ENABLED=0`, so it does not need a remote model key to verify the dashboard flow.

## Configuration

| Variable | Description |
| --- | --- |
| `BUB_MARIMO_HOST` | Bind host (default: `127.0.0.1`) |
| `BUB_MARIMO_PORT` | Bind port (default: `2718`) |
| `BUB_MARIMO_WORKSPACE` | Override the Bub workspace root used for runtime notebook output |
| `BUB_WORKSPACE_PATH` | Default Bub workspace root when `BUB_MARIMO_WORKSPACE` is unset |
