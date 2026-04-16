from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from .errors import LangchainConfigError


class LangchainPluginSettings(BaseSettings):
    """Configuration for the Bubseek LangChain Runnable adapter."""

    model_config = SettingsConfigDict(
        env_prefix="BUB_LANGCHAIN_",
        env_file=".env",
        extra="ignore",
    )

    mode: Literal["", "runnable"] = ""
    factory: str | None = None
    include_bub_tools: bool = True
    tape: bool = True


def load_settings() -> LangchainPluginSettings:
    return LangchainPluginSettings()


def is_enabled(settings: LangchainPluginSettings) -> bool:
    return settings.mode == "runnable"


def validate_config(settings: LangchainPluginSettings) -> None:
    """Raise :class:`LangchainConfigError` when required variables are missing."""

    if settings.mode == "runnable" and not settings.factory:
        raise LangchainConfigError("BUB_LANGCHAIN_FACTORY is required in runnable mode")
