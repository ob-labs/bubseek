"""Configuration for Bubseek bootstrap and tape store resolution."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
)


def discover_project_root(start: Path | str | None = None) -> Path | None:
    """Walk up from start (default cwd) until a directory containing .env is found. Use when package runs from .venv and cwd may not be project root."""
    if start is None:
        start = Path.cwd()
    start = Path(start).resolve()
    for d in [start, *start.parents]:
        if (d / ".env").is_file():
            return d
    return None


def _workspace_env_file() -> Path | None:
    """Return workspace/.env path when BUB_WORKSPACE_PATH is set (only that file, so kernel cwd does not change which .env is loaded)."""
    workspace = os.environ.get("BUB_WORKSPACE_PATH")
    if not workspace:
        return None
    path = Path(workspace).resolve() / ".env"
    if not path.is_file():
        return None
    return path


def env_with_workspace_dotenv(workspace: Path | str) -> dict[str, str]:
    """Merge os.environ with workspace/.env for subprocess env (bub, marimo). Uses python-dotenv like pydantic-settings."""
    from dotenv import dotenv_values

    env = dict(os.environ)
    path = Path(workspace).resolve() / ".env"
    if path.is_file():
        for key, value in dotenv_values(path).items():
            if isinstance(key, str) and isinstance(value, str):
                env[key] = value
    return env


class DatabaseSettings(BaseSettings):
    """Database connection settings for tape store (OceanBase/SeekDB only)."""

    model_config = _SETTINGS_CONFIG

    bub_home: Path = Field(default=Path.home() / ".bub", validation_alias="BUB_HOME")
    tapestore_sqlalchemy_url: str = Field(default="", validation_alias="BUB_TAPESTORE_SQLALCHEMY_URL")

    @property
    def resolved_tapestore_url(self) -> str:
        """Return the explicit tape store URL."""
        return self.tapestore_sqlalchemy_url.strip()

    @property
    def backend_name(self) -> str:
        """Return the normalized SQLAlchemy backend name for the resolved URL."""
        scheme = urlparse(self.resolved_tapestore_url).scheme.lower()
        return scheme.split("+", 1)[0]

    def mysql_connection_params(self) -> tuple[str, int, str, str, str] | None:
        """Return connection params when using a MySQL-compatible backend."""
        if self.backend_name != "mysql":
            return None
        try:
            parsed = urlparse(self.resolved_tapestore_url)
            host = parsed.hostname or ""
            port = parsed.port or 3306
            user = parsed.username or ""
            password = parsed.password or ""
            database = parsed.path.strip("/")
        except Exception:
            return None
        if not host or not database:
            return None
        return host, port, user, password, database


class BubSeekSettings(BaseSettings):
    """Main bubseek configuration."""

    model_config = _SETTINGS_CONFIG

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)

    @classmethod
    def from_workspace(cls, workspace: Path | str | None = None) -> BubSeekSettings:
        """Load settings from workspace .env (pydantic-settings native _env_file). Nested db must get same _env_file."""
        env_file = None
        if workspace is not None:
            path = Path(workspace).resolve() / ".env"
            if path.is_file():
                env_file = path
            else:
                return cls(_env_file=None, db=DatabaseSettings(_env_file=None))  # type: ignore[call-arg]
        if env_file is None:
            env_file = _workspace_env_file()
        if env_file is None:
            return cls(_env_file=None, db=DatabaseSettings(_env_file=None))  # type: ignore[call-arg]
        # Nested BaseSettings does not inherit parent _env_file; pass explicitly (pydantic-settings native)
        return cls(_env_file=env_file, db=DatabaseSettings(_env_file=env_file))  # type: ignore[call-arg]


def resolve_tapestore_url(
    workspace: Path | str | None = None,
    discover_from: Path | str | None = None,
) -> str:
    """Single source of truth for tapestore URL.

    - If workspace is given: use workspace/.env (BubSeekSettings).
    - Else if BUB_WORKSPACE_PATH is set: use that workspace.
    - Else walk discover_from (or cwd) and parents for first .env, use that directory as workspace.
    - Else use process environment only.
    """
    if workspace is not None:
        return BubSeekSettings.from_workspace(workspace).db.resolved_tapestore_url
    env_workspace = os.environ.get("BUB_WORKSPACE_PATH")
    if env_workspace:
        return BubSeekSettings.from_workspace(env_workspace).db.resolved_tapestore_url
    start = Path(discover_from).resolve() if discover_from else Path.cwd().resolve()
    for d in [start, *start.parents]:
        if (d / ".env").is_file():
            return BubSeekSettings.from_workspace(d).db.resolved_tapestore_url
    return BubSeekSettings.from_workspace(None).db.resolved_tapestore_url
