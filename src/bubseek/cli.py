"""Compatibility wrappers for bubseek bootstrap helpers."""

from __future__ import annotations

from bubseek.bootstrap import (
    BubSeekBootstrap,
    create_database,
    database_exists,
)

__all__ = [
    "BubSeekBootstrap",
    "create_database",
    "database_exists",
    "ensure_database",
    "forward_environment",
]


def ensure_database() -> None:
    """Backward-compatible database bootstrap wrapper."""
    BubSeekBootstrap.from_workspace().ensure_database()


def forward_environment(args: list[str] | None = None) -> dict[str, str]:
    """Backward-compatible environment forwarding wrapper."""
    return BubSeekBootstrap.from_workspace().forwarded_environment(args or [])
