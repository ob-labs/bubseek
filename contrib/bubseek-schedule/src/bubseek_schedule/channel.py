import asyncio
from asyncio import Event

from apscheduler.schedulers.base import BaseScheduler
from bub.channels import Channel
from loguru import logger


class ScheduleChannel(Channel):
    def __init__(self, scheduler: BaseScheduler) -> None:
        self.scheduler = scheduler

    async def start(self, stop_event: Event) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self.scheduler.start)
        logger.info("schedule.start complete")

    async def stop(self) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self.scheduler.shutdown)
        logger.info("schedule.stop complete")
