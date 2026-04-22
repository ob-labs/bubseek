import asyncio
import contextlib
from asyncio import Event
from typing import ClassVar

from apscheduler.schedulers import SchedulerAlreadyRunningError
from apscheduler.schedulers.base import BaseScheduler
from bub.channels import Channel
from loguru import logger


class ScheduleChannel(Channel):
    """Starts/stops BackgroundScheduler when this channel is enabled (e.g. gateway)."""

    name: ClassVar[str] = "schedule"

    def __init__(self, scheduler: BaseScheduler) -> None:
        self.scheduler = scheduler

    async def start(self, stop_event: Event) -> None:
        if not self.scheduler.running:
            with contextlib.suppress(SchedulerAlreadyRunningError):
                self.scheduler.start()
        logger.info("schedule.start complete")

    async def stop(self) -> None:
        if not self.scheduler.running:
            logger.info("schedule.stop complete (idle)")
            return
        # BackgroundScheduler.shutdown() blocks until the worker thread stops.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self.scheduler.shutdown(wait=True))
        logger.info("schedule.stop complete")
