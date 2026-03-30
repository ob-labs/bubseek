#!/usr/bin/env bash
# Verify marimo channel E2E. Run from repo root.
# Requires: .env with OPENROUTER_API_KEY (or equivalent) for chat.
set -e
cd "$(dirname "$0")/../.."
uv sync
uv run pytest contrib/bubseek-marimo/tests/test_marimo_e2e.py -v "$@"
