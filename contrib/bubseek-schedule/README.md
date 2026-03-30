# bubseek-schedule

Scheduling plugin for bubseek with OceanBase/SeekDB job store.

## What It Provides

- Bub plugin entry point: `schedule`
- A scheduler channel backed by APScheduler
- OceanBase/SeekDB job store (pyobvector dialect)
- Built-in tools:
  - `schedule.add`
  - `schedule.remove`
  - `schedule.list`

## Installation

bubseek ships `bubseek-schedule` by default. No extra install needed for normal use.

From bubseek repo (development):

```bash
uv add ./contrib/bubseek-schedule
```

Or as dependency (when not using bubseek default):

```toml
[project]
dependencies = [
    "bubseek-schedule @ path:./contrib/bubseek-schedule",
]
```

## Runtime Behavior

- The plugin uses **APScheduler `BackgroundScheduler`** (see also upstream [bub-schedule](https://github.com/bubbuild/bub-contrib) JSON store pattern: persistence must not depend on a specific channel being enabled).
- **`load_state` starts the scheduler** on the first inbound message. That way `bub chat` (CLI-only: only the `cli` channel is enabled) still persists jobs to SeekDB. Previously, `AsyncIOScheduler` was only started by the `schedule` channel, so CLI chat left jobs in memory-only `_pending_jobs` and **nothing was written to `apscheduler_jobs`**.
- The channel name is `schedule`. Enabling it in `bub gateway` is optional for persistence; it still starts/stops the scheduler cleanly when you use gateway with that channel.
- Jobs are persisted to:
  - **OceanBase/SeekDB**: Same URL as the tape store (`BUB_TAPESTORE_SQLALCHEMY_URL`), table `apscheduler_jobs`.

## Provided Tools

- `schedule.add`: Add a scheduled job with cron, interval, or one-shot.
- `schedule.remove`: Remove a scheduled job by ID.
- `schedule.list`: List all scheduled jobs.

## Debug: job in chat but not in Marimo kanban / DB

The gateway resolves the job store URL from `BUB_TAPESTORE_SQLALCHEMY_URL` in the workspace `.env` or process environment. Marimo must use the **same** URL.

From the bubseek repo root:

```bash
uv run python scripts/query_apscheduler_jobs.py --job-id <id>
```
