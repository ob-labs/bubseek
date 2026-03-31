import contextlib

from apscheduler.schedulers import SchedulerAlreadyRunningError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from bub import hookimpl
from bub.types import Envelope, MessageHandler, State

from bubseek_schedule.jobstore import OceanBaseJobStore


def default_scheduler() -> BaseScheduler:
    job_store = OceanBaseJobStore()
    return BackgroundScheduler(jobstores={"default": job_store})


class ScheduleImpl:
    """Schedule plugin: persist jobs to seekdb via OceanBaseJobStore.

    Uses BackgroundScheduler so the scheduler can start without the ``schedule`` channel.
    ``bub chat`` only enables the ``cli`` channel; previously AsyncIOScheduler never started,
    so APScheduler kept jobs in memory-only ``_pending_jobs`` and nothing reached the DB.
    """

    def __init__(self) -> None:
        from bubseek_schedule import tools  # noqa: F401

        self.scheduler = default_scheduler()

    def _ensure_scheduler_started(self) -> None:
        if self.scheduler.running:
            return
        with contextlib.suppress(SchedulerAlreadyRunningError):
            self.scheduler.start()

    @hookimpl
    def load_state(self, message: Envelope, session_id: str) -> State:
        # Runs before tools on every inbound message — covers CLI-only ``bub chat``.
        self._ensure_scheduler_started()
        return {"scheduler": self.scheduler}

    @hookimpl
    def provide_channels(self, message_handler: MessageHandler) -> list:
        from bubseek_schedule.channel import ScheduleChannel

        return [ScheduleChannel(self.scheduler)]


main = ScheduleImpl()
