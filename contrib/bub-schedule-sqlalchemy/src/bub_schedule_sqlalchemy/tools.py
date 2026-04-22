import inspect
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from apscheduler.job import Job
from apscheduler.jobstores.base import ConflictingIdError, JobLookupError
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from bub import tool
from pydantic import BaseModel, Field
from republic import ToolContext

from bub_schedule_sqlalchemy.jobs import run_scheduled_reminder

MISSING_SCHEDULER_MESSAGE = "scheduler not found in state, is ScheduleImpl plugin loaded?"
MISSING_TRIGGER_ARGUMENTS_MESSAGE = "One of after_seconds, interval_seconds, or cron must be set"


def _ensure_scheduler(state: dict) -> BaseScheduler:
    if "scheduler" not in state:
        raise RuntimeError(MISSING_SCHEDULER_MESSAGE)
    return cast(BaseScheduler, state["scheduler"])


def _format_next_run(next_run_time: object) -> str:
    if isinstance(next_run_time, datetime):
        return next_run_time.isoformat()
    return "-"


def _get_job_or_raise(scheduler: BaseScheduler, job_id: str) -> Job:
    job = scheduler.get_job(job_id)
    if job is None:
        raise RuntimeError(f"job not found: {job_id}")
    return job


async def _run_job_now(job: Job) -> None:
    result = job.func(*(job.args or ()), **(job.kwargs or {}))
    if inspect.isawaitable(result):
        await result


class ScheduleAddInput(BaseModel):
    after_seconds: int | None = Field(None, description="If set, schedule to run after this many seconds from now")
    interval_seconds: int | None = Field(None, description="If set, repeat at this interval")
    cron: str | None = Field(
        None,
        description="If set, run with cron expression in crontab format: minute hour day month day_of_week",
    )
    message: str = Field(
        ...,
        description="Reminder message to send, prefix the message with ',' to run a bash command instead",
    )


@tool(name="schedule.add", context=True, model=ScheduleAddInput)
def schedule_add(params: ScheduleAddInput, context: ToolContext) -> str:
    """Schedule a reminder message to be sent to current session in the future."""
    job_id = str(uuid.uuid4())[:8]
    if params.after_seconds is not None:
        trigger = DateTrigger(run_date=datetime.now(UTC) + timedelta(seconds=params.after_seconds))
    elif params.interval_seconds is not None:
        trigger = IntervalTrigger(seconds=params.interval_seconds)
    elif params.cron:
        try:
            trigger = CronTrigger.from_crontab(params.cron)
        except ValueError as exc:
            raise RuntimeError(f"invalid cron expression: {params.cron}") from exc
    else:
        raise RuntimeError(MISSING_TRIGGER_ARGUMENTS_MESSAGE)
    scheduler = _ensure_scheduler(context.state)
    workspace = context.state.get("_runtime_workspace")
    try:
        job = scheduler.add_job(
            run_scheduled_reminder,
            trigger=trigger,
            id=job_id,
            kwargs={
                "message": params.message,
                "session_id": context.state.get("session_id", ""),
                "workspace": str(workspace) if workspace else None,
            },
            coalesce=True,
            max_instances=1,
        )
    except ConflictingIdError as exc:
        raise RuntimeError(f"job id already exists: {job_id}") from exc

    return f"scheduled: {job.id} next={_format_next_run(getattr(job, 'next_run_time', None))}"


@tool(name="schedule.remove", context=True)
def schedule_remove(job_id: str, context: ToolContext) -> str:
    """Remove one scheduled job by id."""
    scheduler = _ensure_scheduler(context.state)
    try:
        scheduler.remove_job(job_id)
    except JobLookupError as exc:
        raise RuntimeError(f"job not found: {job_id}") from exc
    return f"removed: {job_id}"


@tool(name="schedule.list", context=True)
def schedule_list(context: ToolContext) -> str:
    """List scheduled jobs for current workspace."""
    scheduler = _ensure_scheduler(context.state)
    jobs = scheduler.get_jobs()
    rows: list[str] = []
    for job in jobs:
        message = str(job.kwargs.get("message", ""))
        job_session = job.kwargs.get("session_id")
        if job_session and job_session != context.state.get("session_id", ""):
            continue
        rows.append(f"{job.id} next={_format_next_run(getattr(job, 'next_run_time', None))} msg={message}")

    if not rows:
        return "(no scheduled jobs)"

    return "\n".join(rows)


@tool(name="schedule.trigger", context=True)
async def schedule_trigger(job_id: str, context: ToolContext) -> str:
    """Run an existing scheduled job immediately without changing its schedule."""
    scheduler = _ensure_scheduler(context.state)
    job = _get_job_or_raise(scheduler, job_id)
    await _run_job_now(job)

    return f"triggered: {job_id} (next scheduled run: {_format_next_run(job.next_run_time)})"
