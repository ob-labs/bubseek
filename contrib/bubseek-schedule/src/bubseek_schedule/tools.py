import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from apscheduler.jobstores.base import ConflictingIdError, JobLookupError
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from bub import tool
from pydantic import BaseModel, Field
from republic import ToolContext

from bubseek_schedule.jobs import run_scheduled_reminder


def _ensure_scheduler(state: dict) -> BaseScheduler:
    if "scheduler" not in state:
        raise RuntimeError("scheduler not found in state, is ScheduleImpl plugin loaded?")
    return cast(BaseScheduler, state["scheduler"])


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
        raise RuntimeError("One of after_seconds, interval_seconds, or cron must be set")
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

    next_run = "-"
    nrt = getattr(job, "next_run_time", None)
    if isinstance(nrt, datetime):
        next_run = nrt.isoformat()
    return f"scheduled: {job.id} next={next_run}"


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
        next_run = "-"
        nrt = getattr(job, "next_run_time", None)
        if isinstance(nrt, datetime):
            next_run = nrt.isoformat()
        message = str(job.kwargs.get("message", ""))
        job_session = job.kwargs.get("session_id")
        if job_session and job_session != context.state.get("session_id", ""):
            continue
        rows.append(f"{job.id} next={next_run} msg={message}")

    if not rows:
        return "(no scheduled jobs)"

    return "\n".join(rows)
