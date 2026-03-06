# Skills

This directory contains builtin skill source files for `bubseek`.

During wheel builds, these files are staged into `bub_skills/`. Users do not need to run a separate sync step for them.

If you are building a downstream distribution and want to vendor remote skills at build time, use `pdm-build-bub` from your own `pyproject.toml`.
