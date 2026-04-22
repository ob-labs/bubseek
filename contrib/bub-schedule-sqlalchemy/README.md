# bub-schedule-sqlalchemy

`bub-schedule-sqlalchemy` is a Bub plugin that persists APScheduler jobs in a SQLAlchemy-backed store.

It targets the Bub deployment shape where:

- scheduled jobs must survive process restarts
- scheduling must work in `bub chat`
- the same scheduler may also be started by a gateway channel at runtime

The package exposes the Bub plugin entry point `schedule` and uses `BackgroundScheduler`, so scheduler startup is not tied to a specific async event loop or to the `schedule` channel being enabled.

## Installation

Install from the monorepo package directory during local development:

```bash
uv add ./contrib/bub-schedule-sqlalchemy
```

Install directly from GitHub:

```bash
uv pip install "git+https://github.com/ob-labs/bubseek.git#subdirectory=contrib/bub-schedule-sqlalchemy"
```

## Configuration

The plugin reads settings from environment variables:

- `BUB_SCHEDULE_SQLALCHEMY_URL`: primary SQLAlchemy database URL for APScheduler jobs
- `BUB_TAPESTORE_SQLALCHEMY_URL`: fallback URL when the schedule-specific URL is unset
- table name defaults to `apscheduler_jobs`

Resolution order:

1. use `BUB_SCHEDULE_SQLALCHEMY_URL` when set
2. otherwise fall back to `BUB_TAPESTORE_SQLALCHEMY_URL`
3. otherwise scheduler creation may fail and the plugin will log a warning and stay disabled

Example:

```bash
export BUB_SCHEDULE_SQLALCHEMY_URL=sqlite:////tmp/bub-schedule.sqlite
```

Or reuse the shared Bub tapestore:

```bash
export BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://root:@127.0.0.1:2881/bub
```

## Runtime Behavior

`ScheduleImpl` starts the scheduler lazily from `load_state()`, which runs before tools on every inbound message. This is the key behavior that keeps scheduling usable in `bub chat`: even when only the `cli` channel is active, the scheduler is started and jobs are persisted instead of being left in APScheduler's in-memory pending queue.

When the `schedule` channel is enabled in a gateway runtime, `ScheduleChannel` also starts the same scheduler on channel startup and shuts it down cleanly on channel stop.

If scheduler construction fails, the plugin does not crash the framework:

- `load_state()` logs `Schedule plugin disabled: ...` and returns an empty state
- `provide_channels()` logs the same warning and returns no `schedule` channel

## Test-Covered Behavior

Current tests cover these behaviors:

- SQLAlchemy job store round-trip persistence with SQLite
- `ScheduleImpl.load_state()` starts the injected scheduler
- settings resolution from `BUB_SCHEDULE_SQLALCHEMY_URL`
- fallback from `BUB_TAPESTORE_SQLALCHEMY_URL`
- `schedule.trigger` executes both sync and async jobs
- `schedule.trigger` does not shift an interval job's `next_run_time`

## Limitations

- this package only provides scheduling infrastructure; actual reminder delivery still depends on the surrounding Bub runtime and enabled channels
- session scoping is based on the `session_id` stored in job kwargs
- persistence quality and locking semantics depend on the configured SQLAlchemy backend
