# Architecture

This page explains what bubseek is responsible for, and what it deliberately leaves to Bub and normal Python tooling.

## What bubseek does

- provides the `bubseek` executable as a single bootstrap entry point over `bub`
- forwards `.env` values to the Bub subprocess
- normalizes the default tape store to local SQLite while preserving explicit SeekDB/OceanBase support
- ships a small set of builtin skills with the package
- pins a practical default Bub runtime version

## What bubseek does not do

- it does not fork Bub
- it does not define a separate manifest format
- it does not define a separate lockfile format
- it does not define a custom contrib installation workflow

## Responsibility split

### Bub

Bub remains the runtime, command surface, and extension host.

### bubseek

bubseek is the distribution layer: packaging, bootstrap behavior, runtime defaults, and builtin skills.

### Python packaging

Python packaging handles dependency resolution, lockfiles, and installation. Contrib packages stay in that model instead of going through a bubseek-specific workflow.

## Why this split matters

From a user perspective, the benefit is simple: there is less to learn.

- run `bubseek` the same way you would run `bub`
- add contrib the same way you add any Python dependency
- use builtin skills without an extra sync step
- treat generated marimo notebooks as runtime artifacts under `insights/`, not committed templates

That keeps the distribution practical without introducing a second package-management system around Bub.
