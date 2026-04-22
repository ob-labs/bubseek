import contextlib
from collections.abc import Callable, Mapping
from typing import Any

from apscheduler.jobstores.base import BaseJobStore
from apscheduler.schedulers import SchedulerAlreadyRunningError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from bub import hookimpl
from bub.types import Envelope, MessageHandler, State
from loguru import logger

from bub_schedule_sqlalchemy.job_store import ScheduleSQLAlchemySettings, build_sqlalchemy_jobstore

SchedulerFactory = Callable[[], BaseScheduler]


def build_scheduler(*, jobstore: BaseJobStore, jobstore_alias: str = "default") -> BaseScheduler:
    """Build a background scheduler with an injected job store."""
    return BackgroundScheduler(jobstores={jobstore_alias: jobstore})


def build_sqlalchemy_scheduler(
    *,
    settings: ScheduleSQLAlchemySettings,
    engine_options: Mapping[str, Any] | None = None,
    jobstore_alias: str = "default",
) -> BaseScheduler:
    jobstore = build_sqlalchemy_jobstore(settings=settings, engine_options=engine_options)
    return build_scheduler(jobstore=jobstore, jobstore_alias=jobstore_alias)


def _default_scheduler() -> BaseScheduler:
    return build_sqlalchemy_scheduler(settings=ScheduleSQLAlchemySettings())


class ScheduleImpl:
    """Schedule plugin backed by an injected APScheduler scheduler.

    Uses BackgroundScheduler so the scheduler can start without the ``schedule`` channel.
    ``bub chat`` only enables the ``cli`` channel; previously AsyncIOScheduler never started,
    so APScheduler kept jobs in memory-only ``_pending_jobs`` and nothing reached the DB.
    """

    def __init__(self, scheduler_factory: SchedulerFactory) -> None:
        from bub_schedule_sqlalchemy import tools  # noqa: F401

        self._scheduler_factory = scheduler_factory
        self._scheduler: BaseScheduler | None = None

    @classmethod
    def from_scheduler(cls, scheduler: BaseScheduler) -> "ScheduleImpl":
        return cls(lambda: scheduler)

    @property
    def scheduler(self) -> BaseScheduler:
        if self._scheduler is None:
            self._scheduler = self._scheduler_factory()
        return self._scheduler

    def _ensure_scheduler_started(self) -> BaseScheduler:
        scheduler = self.scheduler
        if scheduler.running:
            return scheduler
        with contextlib.suppress(SchedulerAlreadyRunningError):
            scheduler.start()
        return scheduler

    @hookimpl
    def load_state(self, message: Envelope, session_id: str) -> State:
        # Runs before tools on every inbound message — covers CLI-only ``bub chat``.
        try:
            scheduler = self._ensure_scheduler_started()
        except Exception as exc:
            logger.warning(f"Schedule plugin disabled: {exc}")
            return {}
        return {"scheduler": scheduler}

    @hookimpl
    def provide_channels(self, message_handler: MessageHandler) -> list:
        from bub_schedule_sqlalchemy.channel import ScheduleChannel

        try:
            scheduler = self.scheduler
        except Exception as exc:
            logger.warning(f"Schedule plugin disabled: {exc}")
            return []
        return [ScheduleChannel(scheduler)]


main = ScheduleImpl(_default_scheduler)
