"""Tests for bub-schedule-sqlalchemy."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bub_schedule_sqlalchemy import tools
from bub_schedule_sqlalchemy.job_store import (
    ScheduleSQLAlchemySettings,
    build_sqlalchemy_jobstore,
)
from bub_schedule_sqlalchemy.plugin import ScheduleImpl, build_scheduler
from republic import ToolContext


def _test_table_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _sqlite_url(tmp_path, filename: str) -> str:
    return f"sqlite:///{tmp_path / filename}"


def _trigger_result(value: object) -> str:
    result = asyncio.run(value) if asyncio.iscoroutine(value) else value
    assert isinstance(result, str)
    return result


def _trigger(job_id: str, context: ToolContext) -> str:
    handler = tools.schedule_trigger.handler
    if handler is None:
        raise RuntimeError("schedule.trigger handler is not registered")

    return _trigger_result(handler(job_id, context=context))


def test_jobstore_roundtrip_with_sqlite(tmp_path) -> None:
    """Built-in SQLAlchemyJobStore should persist jobs without bubseek helpers."""
    settings = ScheduleSQLAlchemySettings(
        url=_sqlite_url(tmp_path, "roundtrip.sqlite"),
        tablename=_test_table_name("apscheduler_jobs_test_roundtrip"),
    )
    store = build_sqlalchemy_jobstore(settings=settings)
    scheduler = build_scheduler(jobstore=store)
    scheduler.start()

    scheduler.add_job(
        "bub_schedule_sqlalchemy.jobs:_noop",
        "date",
        run_date=datetime.now(UTC) + timedelta(minutes=1),
        id="test-1",
    )
    assert store.lookup_job("test-1") is not None
    jobs = store.get_all_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "test-1"

    scheduler.remove_job("test-1")
    assert store.lookup_job("test-1") is None
    scheduler.shutdown()


def test_schedule_impl_uses_injected_scheduler(tmp_path) -> None:
    settings = ScheduleSQLAlchemySettings(
        url=_sqlite_url(tmp_path, "plugin.sqlite"),
        tablename=_test_table_name("apscheduler_jobs_test_plugin"),
    )
    store = build_sqlalchemy_jobstore(settings=settings)
    scheduler = build_scheduler(jobstore=store)
    plugin = ScheduleImpl.from_scheduler(scheduler)

    async def _message_handler(_message: object) -> None:
        return None

    state = plugin.load_state(message=None, session_id="schedule:test")

    assert state["scheduler"] is scheduler
    assert scheduler.running
    assert [channel.name for channel in plugin.provide_channels(message_handler=_message_handler)] == ["schedule"]


def test_sqlalchemy_settings_support_env(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BUB_SCHEDULE_SQLALCHEMY_URL", _sqlite_url(tmp_path, "env.sqlite"))
    monkeypatch.delenv("BUB_TAPESTORE_SQLALCHEMY_URL", raising=False)

    settings = ScheduleSQLAlchemySettings()

    assert settings.url == _sqlite_url(tmp_path, "env.sqlite")
    assert settings.tablename == "apscheduler_jobs"


def test_sqlalchemy_settings_fallback_to_tapestore_env(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BUB_SCHEDULE_SQLALCHEMY_URL", raising=False)
    monkeypatch.setenv("BUB_TAPESTORE_SQLALCHEMY_URL", _sqlite_url(tmp_path, "tapestore.sqlite"))

    settings = ScheduleSQLAlchemySettings()

    assert settings.url == _sqlite_url(tmp_path, "tapestore.sqlite")
    assert settings.tablename == "apscheduler_jobs"


def test_sqlalchemy_settings_allow_missing_url(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BUB_SCHEDULE_SQLALCHEMY_URL", raising=False)
    monkeypatch.delenv("BUB_TAPESTORE_SQLALCHEMY_URL", raising=False)

    settings = ScheduleSQLAlchemySettings()

    assert settings.url is None
    assert settings.tablename == "apscheduler_jobs"


@pytest.fixture
def scheduler() -> Iterator[BackgroundScheduler]:
    scheduler = BackgroundScheduler()
    scheduler.start()
    yield scheduler
    scheduler.shutdown(wait=False)


@pytest.fixture
def tool_context(scheduler: BackgroundScheduler) -> ToolContext:
    return ToolContext(
        tape=None,
        run_id="test-run",
        state={"scheduler": scheduler, "session_id": "test-session"},
    )


def test_schedule_trigger_executes_sync_job_without_shifting_next_run(
    scheduler: BackgroundScheduler, tool_context: ToolContext
) -> None:
    execution_log: list[dict[str, Any]] = []

    def sync_job(value: str) -> None:
        execution_log.append({"value": value, "timestamp": datetime.now(UTC)})

    next_run = datetime.now(UTC) + timedelta(hours=1)
    scheduler.add_job(
        sync_job,
        trigger=IntervalTrigger(minutes=5),
        id="sync-job",
        kwargs={"value": "payload"},
        next_run_time=next_run,
    )

    result = _trigger("sync-job", tool_context)

    assert len(execution_log) == 1
    assert execution_log[0]["value"] == "payload"
    assert scheduler.get_job("sync-job") is not None
    assert scheduler.get_job("sync-job").next_run_time == next_run
    assert "triggered: sync-job" in result
    assert next_run.isoformat() in result


def test_schedule_trigger_executes_async_job(scheduler: BackgroundScheduler, tool_context: ToolContext) -> None:
    execution_log: list[str] = []

    async def async_job(value: str) -> None:
        await asyncio.sleep(0.01)
        execution_log.append(value)

    scheduler.add_job(
        async_job,
        trigger=IntervalTrigger(minutes=5),
        id="async-job",
        args=["payload"],
        next_run_time=datetime.now(UTC) + timedelta(hours=1),
    )

    result = _trigger("async-job", tool_context)

    assert execution_log == ["payload"]
    assert "triggered: async-job" in result


def test_schedule_trigger_raises_for_missing_job(tool_context: ToolContext) -> None:
    with pytest.raises(RuntimeError, match="job not found: missing-job"):
        _trigger("missing-job", tool_context)
