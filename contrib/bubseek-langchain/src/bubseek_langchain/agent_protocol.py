from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from langchain_core.runnables import Runnable, RunnableConfig
from loguru import logger

from .bridge import LangchainRunContext, extract_prompt_text
from .config import AgentProtocolSettings
from .normalize import normalize_langchain_output

INTERRUPT_KEY = "__interrupt__"


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


def _stream_event_name(part: Any) -> str | None:
    if hasattr(part, "event"):
        event = part.event
        return event if isinstance(event, str) else None
    if isinstance(part, dict):
        event = part.get("event") or part.get("type")
        return event if isinstance(event, str) else None
    return None


def _stream_event_data(part: Any) -> Any:
    if hasattr(part, "data"):
        return part.data
    if isinstance(part, dict):
        return part.get("data")
    return None


def _interrupts_from_stream_part(part: Any) -> list[Any]:
    if isinstance(part, dict):
        interrupts = part.get("interrupts")
        if isinstance(interrupts, list) and interrupts:
            return interrupts

    data = _stream_event_data(part)
    if isinstance(data, Mapping):
        interrupts = data.get(INTERRUPT_KEY)
        if isinstance(interrupts, list) and interrupts:
            return interrupts
    return []


def _raise_for_stream_part(part: Any) -> None:
    event = _stream_event_name(part)
    if event is None:
        return

    if event.startswith("error"):
        detail = normalize_langchain_output(_stream_event_data(part))
        message = detail or "Remote agent-protocol run failed"
        raise AgentProtocolRemoteError(message)

    interrupts = _interrupts_from_stream_part(part)
    if interrupts and (event == "values" or event.startswith("updates")):
        raise AgentProtocolInterruptedError(
            f"Remote agent-protocol run interrupted: {json.dumps(interrupts, ensure_ascii=False, default=str)}"
        )


def _messages_from_stream_part(part: Any) -> tuple[str | None, list[Mapping[str, Any]]]:
    event = _stream_event_name(part)
    data = _stream_event_data(part)
    if event is None:
        return None, []

    if event == "messages" and isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, Mapping):
            return event, [first]
        return event, []

    if event in {"messages/partial", "messages/complete"} and isinstance(data, list):
        return event, [item for item in data if isinstance(item, Mapping)]

    return event, []


def _text_from_message(message: Mapping[str, Any]) -> str:
    return normalize_langchain_output(dict(message))


def _final_state_from_stream_part(part: Any) -> Any | None:
    return _stream_event_data(part) if _stream_event_name(part) == "values" else None


class AgentProtocolRemoteError(RuntimeError):
    """Raised when the remote agent-protocol run returns an explicit error event."""


class AgentProtocolInterruptedError(RuntimeError):
    """Raised when the remote agent-protocol run reports an interrupt."""


class AgentProtocolRunnable(Runnable[Any, Any]):
    """Wrap a remote Bub agent-protocol endpoint as a Bub-oriented Runnable.

    This adapter intentionally accepts Bub prompt shapes or a fully-formed input
    dict. It does not implement general Pregel or RemoteGraph config semantics.
    """

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

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:  # noqa: A002
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ainvoke(input, config=config, **kwargs))
        raise RuntimeError("AgentProtocolRunnable.invoke cannot be used from a running event loop; use ainvoke instead")

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:  # noqa: A002
        thread_id = await self._resolve_thread_id()
        run_input = self._build_run_input(input)
        metadata = self._build_metadata(config)
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

    async def astream(
        self,
        input: Any,  # noqa: A002
        config: RunnableConfig | None = None,
        **kwargs: Any | None,
    ) -> AsyncIterator[str]:
        thread_id = await self._resolve_thread_id()
        run_input = self._build_run_input(input)
        metadata = self._build_metadata(config)
        self._logger.debug(
            "Streaming remote agent-protocol agent={} stateful={} thread_id={}",
            self._settings.agent_id,
            self._settings.stateful,
            thread_id,
        )
        emitted = False
        saw_partial_message = False
        final_state: Any | None = None
        async for part in self._client_instance().runs.stream(
            thread_id=thread_id,
            assistant_id=self._settings.agent_id,
            input=run_input,
            metadata=metadata,
            if_not_exists="create" if thread_id is not None else None,
            stream_mode=["messages", "values", "updates"],
        ):
            _raise_for_stream_part(part)

            maybe_final_state = _final_state_from_stream_part(part)
            if maybe_final_state is not None:
                final_state = maybe_final_state

            event, messages = _messages_from_stream_part(part)
            if event == "messages/partial":
                saw_partial_message = True
            if event == "messages/complete" and saw_partial_message:
                continue

            for message in messages:
                if not _is_assistant_message(message):
                    continue
                text = _text_from_message(message)
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

    def _build_metadata(self, config: Mapping[str, Any] | None) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if self._langchain_context is not None:
            metadata.update(self._langchain_context.as_metadata())

        if not isinstance(config, Mapping):
            return metadata

        config_metadata = config.get("metadata")
        if not isinstance(config_metadata, Mapping):
            return metadata

        for key, value in config_metadata.items():
            if isinstance(key, str):
                metadata[key] = value
        return metadata

    async def _resolve_thread_id(self) -> str | None:
        if not self._settings.stateful or not self._session_id:
            return None
        return self._default_thread_id()

    def _default_thread_id(self) -> str:
        payload = f"{self._settings.url}\0{self._settings.agent_id}\0{self._session_id}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"bubseek-{digest}"
