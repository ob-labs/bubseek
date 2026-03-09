"""OceanBase/SeekDB job store for APScheduler using pyobvector dialect."""

from __future__ import annotations

import pickle
import threading
from datetime import datetime

from apscheduler.job import Job
from apscheduler.jobstores.base import BaseJobStore, ConflictingIdError, JobLookupError
from loguru import logger
from sqlalchemy import case, create_engine, select
from sqlalchemy.orm import sessionmaker

import bubseek.oceanbase  # noqa: F401 - register mysql+oceanbase dialect
from bubseek.config import BubSeekSettings


def _get_jobstore_url() -> str:
    """Get SQLAlchemy URL for job store. Uses tapestore DB (MySQL or SQLite) when configured."""
    settings = BubSeekSettings()
    url = settings.db.tapestore_sqlalchemy_url or ""
    if url:
        # Same DB as tapestore - one DB, multiple tables (tapestore + apscheduler_jobs)
        return url
    # Fallback: no tapestore configured, use standalone SQLite under BUB_HOME
    from bub.builtin.settings import AgentSettings

    home = AgentSettings().home
    job_db = home / "schedule_jobs.db"
    return f"sqlite+pysqlite:///{job_db}"


def _normalize_url(url: str) -> str:
    """Use mysql+oceanbase for pyobvector dialect when mysql is configured."""
    if "mysql" in url.lower() and "oceanbase" not in url.lower():
        return url.replace("mysql+pymysql", "mysql+oceanbase", 1).replace("mysql://", "mysql+oceanbase://", 1)
    return url


class OceanBaseJobStore(BaseJobStore):
    """
    A SQL-based job store for APScheduler using OceanBase/SeekDB (pyobvector) or SQLite.

    Jobs are serialized with pickle and stored in a database table. Uses the same
    database as BUB_TAPESTORE_SQLALCHEMY_URL when configured (MySQL or SQLite) -
    one DB, multiple tables (tapestore + apscheduler_jobs).
    """

    def __init__(self, url: str | None = None, tablename: str = "apscheduler_jobs"):
        super().__init__()
        self._url = _normalize_url(url or _get_jobstore_url())
        self._tablename = tablename
        self._engine = create_engine(self._url, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._lock = threading.RLock()
        self._init_table()

    def _init_table(self) -> None:
        """Create apscheduler_jobs table if not exists."""
        from sqlalchemy import Column, DateTime, LargeBinary, MetaData, String, Table

        metadata = MetaData()
        self._table = Table(
            self._tablename,
            metadata,
            Column("id", String(191), primary_key=True),
            Column("next_run_time", DateTime(timezone=True), nullable=True),
            Column("job_state", LargeBinary, nullable=False),
        )
        metadata.create_all(self._engine)

    def _serialize_job(self, job: Job) -> bytes:
        return pickle.dumps(job, protocol=pickle.HIGHEST_PROTOCOL)

    def _deserialize_job(self, data: bytes) -> Job | None:
        try:
            job = pickle.loads(data)  # noqa: S301
            job._scheduler = self._scheduler
            job._jobstore_alias = self._alias
        except Exception as e:
            logger.error(f"Error deserializing job: {e}")
            return None
        return job

    def start(self, scheduler, alias: str) -> None:
        super().start(scheduler, alias)

    def shutdown(self) -> None:
        with self._lock:
            self._engine.dispose()

    def lookup_job(self, job_id: str) -> Job | None:
        with self._lock, self._session_factory() as session:
            row = session.execute(select(self._table).where(self._table.c.id == job_id)).first()
            if row:
                return self._deserialize_job(row.job_state)
            return None

    def get_due_jobs(self, now: datetime) -> list[Job]:
        with self._lock:
            due_jobs = []
            with self._session_factory() as session:
                stmt = (
                    select(self._table)
                    .where(self._table.c.next_run_time <= now)
                    .where(self._table.c.next_run_time.isnot(None))
                    .order_by(self._table.c.next_run_time)
                )
                rows = session.execute(stmt).all()
                for row in rows:
                    job = self._deserialize_job(row.job_state)
                    if job:
                        due_jobs.append(job)
            return due_jobs

    def get_next_run_time(self) -> datetime | None:
        with self._lock, self._session_factory() as session:
            stmt = (
                select(self._table.c.next_run_time)
                .where(self._table.c.next_run_time.isnot(None))
                .order_by(self._table.c.next_run_time)
                .limit(1)
            )
            row = session.execute(stmt).first()
            return row[0] if row else None

    def get_all_jobs(self) -> list[Job]:
        with self._lock:
            jobs = []
            with self._session_factory() as session:
                # MySQL/OceanBase don't support NULLS LAST; use CASE for compatibility
                next_run = self._table.c.next_run_time
                nulls_last_expr = case((next_run.is_(None), 1), else_=0)
                stmt = select(self._table).order_by(nulls_last_expr.asc(), next_run.asc())
                rows = session.execute(stmt).all()
                for row in rows:
                    job = self._deserialize_job(row.job_state)
                    if job:
                        jobs.append(job)
            return jobs

    def add_job(self, job: Job) -> None:
        with self._lock, self._session_factory() as session:
            existing = session.execute(select(self._table).where(self._table.c.id == job.id)).first()
            if existing:
                raise ConflictingIdError(job.id)
            session.execute(
                self._table.insert().values(
                    id=job.id,
                    next_run_time=job.next_run_time,
                    job_state=self._serialize_job(job),
                )
            )
            session.commit()

    def update_job(self, job: Job) -> None:
        with self._lock, self._session_factory() as session:
            result = session.execute(
                self._table
                .update()
                .where(self._table.c.id == job.id)
                .values(
                    next_run_time=job.next_run_time,
                    job_state=self._serialize_job(job),
                )
            )
            if getattr(result, "rowcount", 0) == 0:
                raise JobLookupError(job.id)
            session.commit()

    def remove_job(self, job_id: str) -> None:
        with self._lock, self._session_factory() as session:
            result = session.execute(self._table.delete().where(self._table.c.id == job_id))
            if getattr(result, "rowcount", 0) == 0:
                raise JobLookupError(job_id)
            session.commit()

    def remove_all_jobs(self) -> None:
        with self._lock, self._session_factory() as session:
            session.execute(self._table.delete())
            session.commit()
