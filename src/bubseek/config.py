"""Configuration for Bubseek bootstrap and tape store resolution."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

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
    """Database connection settings for tape store (OceanBase/SeekDB or SQLite)."""

    model_config = _SETTINGS_CONFIG

    bub_home: Path = Field(default=Path.home() / ".bub", validation_alias="BUB_HOME")
    tapestore_sqlalchemy_url: str = Field(default="", validation_alias="BUB_TAPESTORE_SQLALCHEMY_URL")
    oceanbase_host: str = Field(default="127.0.0.1", validation_alias="OCEANBASE_HOST")
    oceanbase_port: int = Field(default=2881, validation_alias="OCEANBASE_PORT")
    oceanbase_user: str = Field(default="root", validation_alias="OCEANBASE_USER")
    oceanbase_password: str = Field(default="", validation_alias="OCEANBASE_PASSWORD")
    oceanbase_database: str = Field(default="bub", validation_alias="OCEANBASE_DATABASE")

    @property
    def resolved_tapestore_url(self) -> str:
        """Return the explicit tape store URL or Bub's default SQLite path."""
        if self.tapestore_sqlalchemy_url.strip():
            return self.tapestore_sqlalchemy_url.strip()
        database_path = (self.bub_home.expanduser() / "tapes.db").resolve()
        return str(URL.create("sqlite+pysqlite", database=str(database_path)))

    @property
    def backend_name(self) -> str:
        """Return the normalized SQLAlchemy backend name for the resolved URL."""
        scheme = urlparse(self.resolved_tapestore_url).scheme.lower()
        return scheme.split("+", 1)[0]

    def mysql_connection_params(self) -> tuple[str, int, str, str, str] | None:
        """Return connection params when using a MySQL-compatible backend."""
        if self.backend_name != "mysql":
            return None
        host = self.oceanbase_host
        port = self.oceanbase_port
        user = self.oceanbase_user
        password = self.oceanbase_password
        database = self.oceanbase_database
        try:
            parsed = urlparse(self.resolved_tapestore_url)
            if parsed.hostname:
                host = parsed.hostname
            if parsed.port:
                port = parsed.port
            if parsed.username:
                user = parsed.username
            if parsed.password is not None:
                password = parsed.password
            if parsed.path and parsed.path.strip("/"):
                database = parsed.path.strip("/")
        except Exception:  # noqa: S110
            pass
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
    - Else use default (BubSeekSettings.from_workspace(None) → env or ~/.bub/tapes.db).
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
