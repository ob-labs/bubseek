from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bubseek.oceanbase import normalize_oceanbase_url


class BubseekSettings(BaseSettings):
    """Shared runtime settings for Bubseek integrations."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    tapestore_url: str = Field(validation_alias="BUB_TAPESTORE_SQLALCHEMY_URL")

    @field_validator("tapestore_url")
    @classmethod
    def normalize_tapestore_url(cls, value: str) -> str:
        return normalize_oceanbase_url(value)


def load_bubseek_settings() -> BubseekSettings:
    return BubseekSettings()  # ty: ignore[missing-argument]
