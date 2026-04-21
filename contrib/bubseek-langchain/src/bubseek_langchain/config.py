from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field, ValidationError
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


class AgentProtocolSettings(BaseSettings):
    """Configuration for the remote agent-protocol runnable adapter."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    url: str = Field(validation_alias="BUB_AGENT_PROTOCOL_URL")
    agent_id: str = Field(validation_alias="BUB_AGENT_PROTOCOL_AGENT_ID")
    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BUB_AGENT_PROTOCOL_API_KEY", "BUB_API_KEY"),
    )
    stateful: bool = Field(default=True, validation_alias="BUB_AGENT_PROTOCOL_STATEFUL")


def load_settings() -> LangchainPluginSettings:
    return LangchainPluginSettings()


def load_agent_protocol_settings() -> AgentProtocolSettings:
    try:
        return AgentProtocolSettings()
    except ValidationError as exc:
        raise LangchainConfigError(str(exc)) from exc


def is_enabled(settings: LangchainPluginSettings) -> bool:
    return settings.mode == "runnable"


def validate_config(settings: LangchainPluginSettings) -> None:
    """Raise :class:`LangchainConfigError` when required variables are missing."""

    if settings.mode == "runnable" and not settings.factory:
        raise LangchainConfigError("BUB_LANGCHAIN_FACTORY is required in runnable mode")
