"""Configuration for Bubseek bootstrap and tape store resolution."""

from __future__ import annotations

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
