# Architecture

This page explains what bubseek is responsible for, and what it deliberately leaves to Bub and normal Python tooling.

## What bubseek does

- standardizes tape storage on SeekDB/OceanBase
- ships a small set of builtin skills with the package
- bundles a practical set of contrib channels and tools by default
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

bubseek is the distribution layer: packaging, runtime defaults, plugin wiring, and builtin skills.

### Python packaging

Python packaging handles dependency resolution, lockfiles, and installation. Contrib packages stay in that model instead of going through a bubseek-specific workflow.

## Why this split matters

From a user perspective, the benefit is simple: there is less to learn.

- run `bub`
- add contrib the same way you add any Python dependency
- use builtin skills without an extra sync step
- treat generated marimo notebooks as runtime artifacts under `insights/`, not committed templates

That keeps the distribution practical without introducing a second package-management system around Bub.
