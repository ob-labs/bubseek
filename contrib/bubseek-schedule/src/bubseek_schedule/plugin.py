from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import BaseScheduler
from bub import hookimpl
from bub.types import Envelope, MessageHandler, State

from bubseek_schedule.jobstore import OceanBaseJobStore


def default_scheduler() -> BaseScheduler:
    job_store = OceanBaseJobStore()
    return AsyncIOScheduler(jobstores={"default": job_store})


class ScheduleImpl:
    def __init__(self) -> None:
        from bubseek_schedule import tools  # noqa: F401

        self.scheduler = default_scheduler()

    @hookimpl
    def load_state(self, message: Envelope, session_id: str) -> State:
        return {"scheduler": self.scheduler}

    @hookimpl
    def provide_channels(self, message_handler: MessageHandler) -> list:
        from bubseek_schedule.channel import ScheduleChannel

        return [ScheduleChannel(self.scheduler)]


main = ScheduleImpl()
