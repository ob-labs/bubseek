"""Tests for bubseek-schedule (OceanBaseJobStore)."""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ.pop("BUB_TAPESTORE_SQLALCHEMY_URL", None)


def test_jobstore_in_memory():
    """Test jobstore with in-memory SQLite via APScheduler."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from bubseek_schedule.jobstore import OceanBaseJobStore

    store = OceanBaseJobStore(url="sqlite:///:memory:")
    scheduler = BackgroundScheduler(jobstores={"default": store})
    scheduler.start()

    scheduler.add_job("bubseek_schedule.jobs:_noop", "date", run_date=datetime.now(), id="test-1")
    assert store.lookup_job("test-1") is not None
    jobs = store.get_all_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "test-1"

    scheduler.remove_job("test-1")
    assert store.lookup_job("test-1") is None
    scheduler.shutdown()


def test_jobstore_tapestore_sqlite_same_db():
    """Test jobstore uses tapestore SQLite - same DB, same file, multiple tables."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "bub.db"
        url = f"sqlite+pysqlite:///{db_path}"

        # Simulate tapestore having a table
        from sqlalchemy import Column, MetaData, String, Table, create_engine, text

        engine = create_engine(url)
        metadata = MetaData()
        Table("tapestore_dummy", metadata, Column("id", String(50), primary_key=True))
        metadata.create_all(engine)

        # Jobstore uses same URL - should add apscheduler_jobs table
        from apscheduler.schedulers.background import BackgroundScheduler
        from bubseek_schedule.jobstore import OceanBaseJobStore

        store = OceanBaseJobStore(url=url)
        scheduler = BackgroundScheduler(jobstores={"default": store})
        scheduler.start()

        run_date = datetime.now() + timedelta(hours=1)  # Future so scheduler won't run/remove before shutdown
        scheduler.add_job("bubseek_schedule.jobs:_noop", "date", run_date=run_date, id="test-2")
        assert store.lookup_job("test-2") is not None

        # Verify both tables exist in same DB
        with engine.connect() as conn:
            tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()
        table_names = [t[0] for t in tables]
        assert "apscheduler_jobs" in table_names
        assert "tapestore_dummy" in table_names

        scheduler.shutdown()


def test_jobstore_get_due_jobs():
    """Test get_due_jobs and get_next_run_time."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from bubseek_schedule.jobstore import OceanBaseJobStore

    store = OceanBaseJobStore(url="sqlite:///:memory:")
    scheduler = BackgroundScheduler(jobstores={"default": store})
    scheduler.start()

    now = datetime.now()
    past = now - timedelta(minutes=1)
    future = now + timedelta(hours=1)

    scheduler.add_job("bubseek_schedule.jobs:_noop", "date", run_date=past, id="past")
    scheduler.add_job("bubseek_schedule.jobs:_noop", "date", run_date=future, id="future")

    due = store.get_due_jobs(now)
    assert len(due) == 1
    assert due[0].id == "past"

    next_run = store.get_next_run_time()
    assert next_run is not None
    assert next_run <= now

    scheduler.shutdown()
