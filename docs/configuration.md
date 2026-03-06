# Configuration

bubseek uses standard Python packaging metadata from `pyproject.toml`.

Most users only need to care about two things:

1. which Bub version is pinned
2. which contrib packages are installed

## Pin Bub

Pin Bub like a normal dependency:

```toml
[project]
dependencies = [
    "bub==0.3.0a1",
]
```

## Add contrib packages

Treat contrib as ordinary Python packages. For Git-hosted contrib packages, use direct references:

```toml
[project]
dependencies = [
    "bub==0.3.0a1",
    "bub-codex @ git+https://github.com/bubbuild/bub-contrib.git@main#subdirectory=packages/bub-codex",
]
```

If you do not want them installed by default, put them under `optional-dependencies` instead.

## Runtime credentials

bubseek forwards `.env` values to the Bub subprocess. A typical setup looks like this:

```dotenv
bub_api_key=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

## Builtin skills

Builtin skill source files live in `skills/`. During wheel builds they are staged into `bub_skills/`, which Bub already knows how to discover. Users do not need to run a separate sync command for them.

## Advanced: downstream skill packaging

Most users can skip this section.

If you are building your own downstream Bub distribution and want to vendor remote skill repositories at build time, use `pdm-build-bub`:

```toml
[build-system]
requires = ["pdm-backend", "pdm-build-bub==0.1.0a1"]
build-backend = "pdm.backend"

[tool.bub]
skills = [
    { git = "PsiACE/skills", include = ["python-*"] },
    { git = "https://github.com/example/skills.git", ref = "v1.2.3", subpath = "skills/review" },
]
```
