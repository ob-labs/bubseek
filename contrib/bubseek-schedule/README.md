# bubseek-schedule

Scheduling plugin for bubseek with OceanBase/SeekDB job store.

## What It Provides

- Bub plugin entry point: `schedule`
- A scheduler channel backed by APScheduler
- OceanBase/SeekDB job store (pyobvector dialect) or SQLite fallback
- Built-in tools:
  - `schedule.add`
  - `schedule.remove`
  - `schedule.list`

## Installation

From bubseek repo (development):

```bash
uv add ./contrib/bubseek-schedule
```

Or as dependency:

```toml
[project]
dependencies = [
    "bubseek-schedule @ path:./contrib/bubseek-schedule",
]
```

## Runtime Behavior

- Scheduler starts when the plugin channel starts.
- Jobs are persisted to:
  - **OceanBase/SeekDB**: When `BUB_TAPESTORE_SQLALCHEMY_URL` uses `mysql+oceanbase`, jobs go to the same database (table `apscheduler_jobs`).
  - **SQLite fallback**: `<BUB_HOME>/schedule_jobs.db` when no MySQL URL is configured.

## Provided Tools

- `schedule.add`: Add a scheduled job with cron, interval, or one-shot.
- `schedule.remove`: Remove a scheduled job by ID.
- `schedule.list`: List all scheduled jobs.
