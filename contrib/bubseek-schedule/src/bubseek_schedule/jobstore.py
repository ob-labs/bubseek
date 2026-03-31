"""OceanBase/seekdb job store for APScheduler using pyobvector dialect."""

from __future__ import annotations

import pickle
import threading
from datetime import datetime

from apscheduler.job import Job
from apscheduler.jobstores.base import BaseJobStore, ConflictingIdError, JobLookupError
from loguru import logger
from sqlalchemy import Table, case, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import sessionmaker as sessionmaker_type

import bubseek.oceanbase  # noqa: F401 - register mysql+oceanbase dialect


def _get_jobstore_url() -> str:
    """Resolve tapestore URL (workspace .env, BUB_WORKSPACE_PATH, cwd) like the rest of bubseek."""
    from bubseek.config import resolve_tapestore_url

    return resolve_tapestore_url()


def _normalize_url(url: str) -> str:
    """Use mysql+oceanbase for pyobvector dialect when mysql is configured."""
    if "mysql" in url.lower() and "oceanbase" not in url.lower():
        return url.replace("mysql+pymysql", "mysql+oceanbase", 1).replace("mysql://", "mysql+oceanbase://", 1)
    return url


class OceanBaseJobStore(BaseJobStore):
    """
    A SQL-based job store for APScheduler using OceanBase/seekdb (pyobvector).

    Jobs are serialized with pickle and stored in a database table. Uses the same
    database as BUB_TAPESTORE_SQLALCHEMY_URL - one DB, multiple tables
    (tapestore + apscheduler_jobs).
    """

    def __init__(self, url: str | None = None, tablename: str = "apscheduler_jobs"):
        super().__init__()
        self._url_explicit = url
        self._tablename = tablename
        self._engine: Engine | None = None
        self._session_factory: sessionmaker_type | None = None
        self._table: Table | None = None
        self._lock = threading.RLock()

    def _connection_url(self) -> str:
        if self._url_explicit is not None:
            return _normalize_url(self._url_explicit)
        return _normalize_url(_get_jobstore_url())

    def _ensure_initialized(self) -> None:
        if self._engine is not None and self._session_factory is not None and self._table is not None:
            return
        self._engine = create_engine(self._connection_url(), pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._init_table()

    def _init_table(self) -> None:
        """Create apscheduler_jobs table if not exists."""
        from sqlalchemy import Column, DateTime, LargeBinary, MetaData, String

        if self._engine is None:
            raise RuntimeError("jobstore engine not initialized")

        metadata = MetaData()
        self._table = Table(
            self._tablename,
            metadata,
            Column("id", String(191), primary_key=True),
            Column("next_run_time", DateTime(timezone=True), nullable=True),
            Column("job_state", LargeBinary, nullable=False),
        )
        metadata.create_all(self._engine)

    def _session_factory_or_raise(self) -> sessionmaker_type:
        self._ensure_initialized()
        if self._session_factory is None:
            raise RuntimeError("jobstore session factory not initialized")
        return self._session_factory

    def _table_or_raise(self) -> Table:
        self._ensure_initialized()
        if self._table is None:
            raise RuntimeError("jobstore table not initialized")
        return self._table

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
        self._ensure_initialized()

    def shutdown(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.dispose()

    def lookup_job(self, job_id: str) -> Job | None:
        session_factory = self._session_factory_or_raise()
        table = self._table_or_raise()
        with self._lock, session_factory() as session:
            row = session.execute(select(table).where(table.c.id == job_id)).first()
            if row:
                return self._deserialize_job(row.job_state)
            return None

    def get_due_jobs(self, now: datetime) -> list[Job]:
        session_factory = self._session_factory_or_raise()
        table = self._table_or_raise()
        with self._lock:
            due_jobs = []
            with session_factory() as session:
                stmt = (
                    select(table)
                    .where(table.c.next_run_time <= now)
                    .where(table.c.next_run_time.isnot(None))
                    .order_by(table.c.next_run_time)
                )
                rows = session.execute(stmt).all()
                for row in rows:
                    job = self._deserialize_job(row.job_state)
                    if job:
                        due_jobs.append(job)
            return due_jobs

    def get_next_run_time(self) -> datetime | None:
        session_factory = self._session_factory_or_raise()
        table = self._table_or_raise()
        with self._lock, session_factory() as session:
            stmt = (
                select(table.c.next_run_time)
                .where(table.c.next_run_time.isnot(None))
                .order_by(table.c.next_run_time)
                .limit(1)
            )
            row = session.execute(stmt).first()
            return row[0] if row else None

    def get_all_jobs(self) -> list[Job]:
        session_factory = self._session_factory_or_raise()
        table = self._table_or_raise()
        with self._lock:
            jobs = []
            with session_factory() as session:
                # MySQL/OceanBase don't support NULLS LAST; use CASE for compatibility
                next_run = table.c.next_run_time
                nulls_last_expr = case((next_run.is_(None), 1), else_=0)
                stmt = select(table).order_by(nulls_last_expr.asc(), next_run.asc())
                rows = session.execute(stmt).all()
                for row in rows:
                    job = self._deserialize_job(row.job_state)
                    if job:
                        jobs.append(job)
            return jobs

    def add_job(self, job: Job) -> None:
        session_factory = self._session_factory_or_raise()
        table = self._table_or_raise()
        with self._lock, session_factory() as session:
            existing = session.execute(select(table).where(table.c.id == job.id)).first()
            if existing:
                raise ConflictingIdError(job.id)
            session.execute(
                table.insert().values(
                    id=job.id,
                    next_run_time=job.next_run_time,
                    job_state=self._serialize_job(job),
                )
            )
            session.commit()

    def update_job(self, job: Job) -> None:
        session_factory = self._session_factory_or_raise()
        table = self._table_or_raise()
        with self._lock, session_factory() as session:
            result = session.execute(
                table
                .update()
                .where(table.c.id == job.id)
                .values(
                    next_run_time=job.next_run_time,
                    job_state=self._serialize_job(job),
                )
            )
            if getattr(result, "rowcount", 0) == 0:
                raise JobLookupError(job.id)
            session.commit()

    def remove_job(self, job_id: str) -> None:
        session_factory = self._session_factory_or_raise()
        table = self._table_or_raise()
        with self._lock, session_factory() as session:
            result = session.execute(table.delete().where(table.c.id == job_id))
            if getattr(result, "rowcount", 0) == 0:
                raise JobLookupError(job_id)
            session.commit()

    def remove_all_jobs(self) -> None:
        session_factory = self._session_factory_or_raise()
        table = self._table_or_raise()
        with self._lock, session_factory() as session:
            session.execute(table.delete())
            session.commit()
