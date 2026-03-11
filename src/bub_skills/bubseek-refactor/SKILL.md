---
name: bubseek-refactor
description: Refactor a Bub-based distribution with a single bootstrap entry point, explicit runtime defaults, and generated insight assets.
---

# Bubseek Refactor

Use this skill when refactoring a Bub-based Python distribution such as `bubseek`.

## Goals

- Keep one clear bootstrap entry point for the distribution.
- Preserve production capabilities such as SeekDB or OceanBase support.
- Use SQLite only as a local or test-friendly default when no remote store is configured.
- Generate runtime insight notebooks from one canonical source instead of committing duplicates.
- Keep `make check` and `make test` green after each refactor slice.

## Design Rules

1. Separate parsing or wiring from runtime behavior.
2. Prefer one public bootstrap object over scattered helper functions.
3. Distinguish production support from local defaults.
4. Treat generated notebooks and dashboards as runtime artifacts, not hand-maintained source files.
5. Make E2E tests deterministic and offline-friendly when possible.

## Refactor Workflow

1. Map the current entry points, environment variables, and runtime side effects.
2. Move bootstrap logic into one module with a small public surface.
3. Normalize configuration so default SQLite behavior and explicit SeekDB or OceanBase URLs are both clear.
4. Centralize notebook templates or generated assets in one package module.
5. Delete repository copies of generated artifacts and ignore regenerated runtime files.
6. Expand tests around the public entry point and configuration resolution.
7. Run `make check` and `make test` before each commit.

## Frost Ming Style Notes

- Provide a simple default path first, then expose advanced behavior through explicit parameters.
- Hide internal wiring behind a small entry point.
- Prefer thin wrappers, stable return types, and change-isolated modules.
- Reduce duplication by pulling repeated logic into shared modules before renaming or polishing details.
