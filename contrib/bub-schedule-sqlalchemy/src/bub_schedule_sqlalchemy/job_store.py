from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScheduleSQLAlchemySettings(BaseSettings):
    """Configuration for the APScheduler SQLAlchemy job store."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    url: str | None = Field(default=None, validation_alias="BUB_SCHEDULE_SQLALCHEMY_URL")
    tapestore_url: str | None = Field(default=None, validation_alias="BUB_TAPESTORE_SQLALCHEMY_URL", exclude=True)
    tablename: str = "apscheduler_jobs"

    @model_validator(mode="after")
    def inherit_tapestore_url(self) -> ScheduleSQLAlchemySettings:
        if self.url is None and self.tapestore_url:
            self.url = self.tapestore_url
        return self


def build_sqlalchemy_jobstore(
    *,
    settings: ScheduleSQLAlchemySettings,
    engine_options: Mapping[str, Any] | None = None,
) -> SQLAlchemyJobStore:
    return SQLAlchemyJobStore(
        url=settings.url,
        tablename=settings.tablename,
        engine_options=dict(engine_options or {}),
    )
