from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Mapping
from typing import Any

from langchain_core.runnables import Runnable
from loguru import logger

from .bridge import LangchainRunContext, extract_prompt_text
from .config import AgentProtocolSettings
from .normalize import normalize_langchain_output


def _bind_logger(run_context: LangchainRunContext | None):
    if run_context is None:
        return logger
    return logger.bind(**run_context.as_logger_extra())


def _message_role(message: Mapping[str, Any]) -> str | None:
    for key in ("role", "type"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _is_assistant_message(message: Mapping[str, Any]) -> bool:
    role = _message_role(message)
    if role is None:
        return True
    return role in {"assistant", "ai", "aimessage", "aimessagechunk"}


def _messages_from_stream_part(part: Any) -> list[Mapping[str, Any]]:
    if hasattr(part, "event") and hasattr(part, "data"):
        event = part.event
        data = part.data
        if event == "messages" and isinstance(data, list) and data:
            first = data[0]
            return [first] if isinstance(first, Mapping) else []
        if event in {"messages/partial", "messages/complete"} and isinstance(data, list):
            return [item for item in data if isinstance(item, Mapping)]
        return []

    if not isinstance(part, dict):
        return []
    part_type = part.get("type") or part.get("event")
    data = part.get("data")
    if part_type == "messages" and isinstance(data, list) and data:
        first = data[0]
        return [first] if isinstance(first, Mapping) else []
    if part_type in {"messages/partial", "messages/complete"} and isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    return []


def _final_state_from_stream_part(part: Any) -> Any | None:
    if hasattr(part, "event") and hasattr(part, "data"):
        return part.data if part.event == "values" else None
    if isinstance(part, dict) and (part.get("type") == "values" or part.get("event") == "values"):
        return part.get("data")
    return None


class AgentProtocolRunnable(Runnable[Any, Any]):
    """Wrap a remote agent-protocol server as a LangChain-compatible Runnable."""

    def __init__(
        self,
        *,
        settings: AgentProtocolSettings,
        session_id: str | None,
        langchain_context: LangchainRunContext | None = None,
    ) -> None:
        self._settings = settings
        self._session_id = session_id
        self._langchain_context = langchain_context
        self._logger = _bind_logger(langchain_context)
        self._client: Any | None = None

    def invoke(self, value: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ainvoke(value, config=config, **kwargs))
        raise RuntimeError("AgentProtocolRunnable.invoke cannot be used from a running event loop; use ainvoke instead")

    async def ainvoke(self, value: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        thread_id = await self._resolve_thread_id()
        run_input = self._build_run_input(value)
        metadata = self._build_metadata()
        self._logger.debug(
            "Invoking remote agent-protocol agent={} stateful={} thread_id={}",
            self._settings.agent_id,
            self._settings.stateful,
            thread_id,
        )
        return await self._client_instance().runs.wait(
            thread_id=thread_id,
            assistant_id=self._settings.agent_id,
            input=run_input,
            metadata=metadata,
            if_not_exists="create" if thread_id is not None else None,
        )

    async def astream(self, value: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> AsyncIterator[str]:
        thread_id = await self._resolve_thread_id()
        run_input = self._build_run_input(value)
        metadata = self._build_metadata()
        self._logger.debug(
            "Streaming remote agent-protocol agent={} stateful={} thread_id={}",
            self._settings.agent_id,
            self._settings.stateful,
            thread_id,
        )
        emitted = False
        final_state: Any | None = None
        async for part in self._client_instance().runs.stream(
            thread_id=thread_id,
            assistant_id=self._settings.agent_id,
            input=run_input,
            metadata=metadata,
            if_not_exists="create" if thread_id is not None else None,
            stream_mode=["messages", "values"],
        ):
            maybe_final_state = _final_state_from_stream_part(part)
            if maybe_final_state is not None:
                final_state = maybe_final_state

            for message in _messages_from_stream_part(part):
                if not _is_assistant_message(message):
                    continue
                text = normalize_langchain_output(dict(message))
                if not text:
                    continue
                emitted = True
                yield text

        if not emitted and final_state is not None:
            fallback_text = normalize_langchain_output(final_state)
            if fallback_text:
                yield fallback_text

    def _client_instance(self) -> Any:
        if self._client is None:
            from langgraph_sdk import get_client

            client_kwargs: dict[str, Any] = {"url": self._settings.url}
            if self._settings.api_key is not None:
                client_kwargs["api_key"] = self._settings.api_key
            self._client = get_client(**client_kwargs)
        return self._client

    def _build_run_input(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        prompt_text = extract_prompt_text(value) if isinstance(value, str | list) else normalize_langchain_output(value)
        return {"messages": [{"role": "user", "content": prompt_text}]}

    def _build_metadata(self) -> dict[str, str]:
        if self._langchain_context is None:
            return {}
        return self._langchain_context.as_metadata()

    async def _resolve_thread_id(self) -> str | None:
        if not self._settings.stateful or not self._session_id:
            return None
        return self._default_thread_id()

    def _default_thread_id(self) -> str:
        payload = f"{self._settings.url}\0{self._settings.agent_id}\0{self._session_id}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"bubseek-{digest}"
