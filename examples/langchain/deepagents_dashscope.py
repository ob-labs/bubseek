from __future__ import annotations

import importlib
import os
from functools import wraps
from typing import Any

from bubseek_langchain.bridge import LangchainRunContext, extract_prompt_text
from loguru import logger

DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_DEEPAGENTS_MODEL = "glm-5.1"


class DashScopeExampleError(RuntimeError):
    """Base error for the DashScope deepagents example."""


class MissingDashScopeEnvError(DashScopeExampleError):
    """Raised when a required DashScope environment variable is missing."""

    def __init__(self, name: str) -> None:
        super().__init__(f"{name} is required for the DashScope deepagents example")


class MissingLangChainOpenAIError(DashScopeExampleError):
    """Raised when langchain-openai is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "langchain-openai is required for the DashScope deepagents example. Install the langchain extra first."
        )


def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


def _bind_logger(langchain_context: LangchainRunContext | None):
    if langchain_context is None:
        return logger
    return logger.bind(**langchain_context.as_logger_extra())


def _require_env(name: str, *, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value and value.strip():
        return value.strip()
    raise MissingDashScopeEnvError(name)


def _resolve_deepagents_model() -> str:
    configured_model = os.getenv("BUB_DEEPAGENTS_MODEL") or os.getenv("BUB_MODEL", DEFAULT_DEEPAGENTS_MODEL)
    model = configured_model.strip()
    if ":" in model:
        _, resolved_model = model.split(":", 1)
        return resolved_model.strip()
    return model


def _build_chat_model(bound_logger: Any | None = None) -> Any:
    active_logger = bound_logger or _bind_logger(None)
    try:
        module = importlib.import_module("langchain_openai")
    except ModuleNotFoundError as exc:
        active_logger.exception("DashScope example missing dependency langchain_openai")
        raise MissingLangChainOpenAIError from exc

    chat_openai_cls: Any = module.ChatOpenAI
    model_name = _resolve_deepagents_model()
    base_url = os.getenv("BUB_DEEPAGENTS_API_BASE") or os.getenv("BUB_API_BASE", DEFAULT_DASHSCOPE_BASE_URL)
    active_logger.info("Building DashScope chat model model={} base_url={}", model_name, base_url)
    chat_model_kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": os.getenv("BUB_DEEPAGENTS_API_KEY") or _require_env("BUB_API_KEY"),
        "base_url": base_url,
        "temperature": 0,
    }

    return chat_openai_cls(**chat_model_kwargs)


def _build_weather_tool(bound_logger: Any):
    @wraps(get_weather)
    def logged_weather(city: str) -> str:
        bound_logger.info("DeepAgents weather tool called city={}", city)
        return get_weather(city)

    return logged_weather


def dashscope_deep_agent(
    *,
    tools: list[Any] | None = None,
    system_prompt: str = "",
    prompt: str | list[dict[str, Any]],
    langchain_context: LangchainRunContext | None = None,
    **_: Any,
) -> tuple[Any, dict[str, list[dict[str, str]]]]:
    """Build a DeepAgents runnable backed by DashScope's OpenAI-compatible API."""

    from deepagents import create_deep_agent
    from langchain_core.runnables import RunnableLambda

    bound_logger = _bind_logger(langchain_context)
    prompt_text = extract_prompt_text(prompt)
    bound_logger.info(
        "Building DeepAgents DashScope runnable tool_count={} prompt_chars={}",
        len(tools or []),
        len(prompt_text),
    )

    agent = create_deep_agent(
        model=_build_chat_model(bound_logger),
        tools=[_build_weather_tool(bound_logger), *(tools or [])],
        system_prompt=system_prompt or "You are a helpful assistant",
    )
    bound_logger.info("Created DeepAgents agent bubbled_tools={}", len(tools or []))
    runnable = agent | RunnableLambda(lambda state: state["messages"][-1].content)
    invoke_input = {"messages": [{"role": "user", "content": prompt_text}]}
    bound_logger.debug("Prepared DeepAgents invoke input message_count={}", len(invoke_input["messages"]))
    return runnable, invoke_input
