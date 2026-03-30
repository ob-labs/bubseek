"""Tests for bubseek-schedule (OceanBaseJobStore)."""

import os
from datetime import datetime, timedelta

import pytest


def _seekdb_url() -> str:
    url = (os.environ.get("BUB_TAPESTORE_SQLALCHEMY_URL") or "").strip()
    if not url:
        pytest.skip("BUB_TAPESTORE_SQLALCHEMY_URL is required for schedule tests")
    if "mysql" not in url and "oceanbase" not in url:
        pytest.skip("schedule tests require a SeekDB/OceanBase URL")
    return url


def test_jobstore_roundtrip():
    """Test jobstore roundtrip via APScheduler on SeekDB/OceanBase."""
    from apscheduler.schedulers.background import BackgroundScheduler

    url = _seekdb_url()
    from bubseek_schedule.jobstore import OceanBaseJobStore

    store = OceanBaseJobStore(url=url, tablename="apscheduler_jobs_test_roundtrip")
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


def test_jobstore_get_due_jobs():
    """Test get_due_jobs and get_next_run_time."""
    from apscheduler.schedulers.background import BackgroundScheduler

    url = _seekdb_url()
    from bubseek_schedule.jobstore import OceanBaseJobStore

    store = OceanBaseJobStore(url=url, tablename="apscheduler_jobs_test_due")
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
