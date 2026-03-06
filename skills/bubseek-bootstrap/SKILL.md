---
name: bubseek-bootstrap
description: Bubseek bootstrap skill for wrapper-based Bub environments.
---

# Bubseek Bootstrap

Use this skill when a task is about bootstrapping or inspecting a `bubseek` environment.

## Runtime Model

- Run Bub commands through `bubseek`.
- Pass runtime credentials through `.env`.
- Add contrib as normal Python dependencies.

## Packaging Model

1. Pin Bub in `pyproject.toml`.
2. Install contrib through standard dependency management.
3. Ship builtin skills with the distribution.
