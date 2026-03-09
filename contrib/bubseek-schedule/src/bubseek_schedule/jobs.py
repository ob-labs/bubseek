from __future__ import annotations

from pathlib import Path

from bub import BubFramework
from bub.channels.message import ChannelMessage

SCHEDULE_SUBPROCESS_TIMEOUT_SECONDS = 300


def _noop() -> None:
    """No-op for tests (must be module-level for pickle ref)."""
    pass


async def run_scheduled_reminder(message: str, session_id: str, workspace: str | None = None) -> None:
    framework = BubFramework()
    framework.load_hooks()
    if workspace:
        framework.workspace = Path(workspace).resolve()
    if ":" in session_id:
        channel, chat_id = session_id.split(":", 1)
    else:
        channel = "schedule"
        chat_id = "default"
    payload = ChannelMessage(
        content=message,
        session_id=session_id,
        channel=channel,
        chat_id=chat_id,
    )
    await framework.process_inbound(payload)
