from __future__ import annotations

import json
from typing import Any, Protocol

from langchain_core.callbacks import AsyncCallbackHandler
from republic import TapeEntry

from .normalize import normalize_langchain_output


class TapeAppender(Protocol):
    async def append_async(self, entry: TapeEntry) -> None: ...


class LangchainTapeCallbackHandler(AsyncCallbackHandler):
    """Append LangChain tool spans to the active Bub tape."""

    def __init__(
        self,
        tape: TapeAppender,
        *,
        session_id: str | None = None,
        tape_name: str | None = None,
        root_run_id: str | None = None,
    ) -> None:
        super().__init__()
        self._tape = tape
        self._shared_meta: dict[str, str] = {}
        if session_id:
            self._shared_meta["session_id"] = session_id
        if tape_name:
            self._shared_meta["tape_name"] = tape_name
        if root_run_id:
            self._shared_meta["langchain_run_id"] = root_run_id

    def _entry_meta(self, **meta: Any) -> dict[str, Any]:
        entry_meta: dict[str, Any] = dict(self._shared_meta)
        entry_meta.update({key: value for key, value in meta.items() if value is not None})
        return entry_meta

    async def _append_event(
        self,
        name: str,
        *,
        data: dict[str, Any] | None = None,
        **meta: Any,
    ) -> None:
        await self._tape.append_async(TapeEntry.event(name, data=data, **self._entry_meta(**meta)))

    async def _append_error_event(
        self,
        name: str,
        error: BaseException,
        **meta: Any,
    ) -> None:
        await self._append_event(name, data={"error": str(error)}, **meta)

    def _jsonable(self, value: Any) -> Any:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self._jsonable(item) for item in value]
        if hasattr(value, "content"):
            return normalize_langchain_output(value)
        try:
            json.dumps(value)
        except TypeError:
            return str(value)
        return value

    def _serialized_name(self, serialized: Any) -> str:
        if not isinstance(serialized, dict):
            return str(serialized or "unknown")
        return str(serialized.get("name") or serialized.get("id") or "unknown")

    async def _append_run_event(
        self,
        name: str,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_data = dict(data or {})
        if tags:
            event_data["tags"] = list(tags)
        if metadata:
            event_data["metadata"] = self._jsonable(metadata)
        await self._append_event(
            name,
            data=event_data or None,
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id is not None else None,
        )

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        name = self._serialized_name(serialized)
        await self._tape.append_async(
            TapeEntry.tool_call(
                calls=[
                    {
                        "id": str(run_id),
                        "type": "function",
                        "function": {
                            "name": str(name),
                            "arguments": input_str or "{}",
                        },
                    }
                ],
                **self._entry_meta(
                    parent_run_id=str(parent_run_id) if parent_run_id is not None else None,
                    run_id=str(run_id),
                    tags=tags,
                    metadata=metadata,
                ),
            )
        )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        **_: Any,
    ) -> None:
        await self._tape.append_async(
            TapeEntry.tool_result(
                results=[normalize_langchain_output(output)],
                **self._entry_meta(
                    run_id=str(run_id),
                    parent_run_id=str(parent_run_id) if parent_run_id is not None else None,
                    tags=tags,
                ),
            )
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        **_: Any,
    ) -> None:
        await self._tape.append_async(
            TapeEntry.tool_result(
                results=[{"error": str(error)}],
                **self._entry_meta(
                    run_id=str(run_id),
                    parent_run_id=str(parent_run_id) if parent_run_id is not None else None,
                    tags=tags,
                ),
            )
        )

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        await self._append_run_event(
            "langchain.chain.start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            data={
                "name": self._serialized_name(serialized),
                "inputs": self._jsonable(inputs),
            },
            tags=tags,
            metadata=metadata,
        )

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        **_: Any,
    ) -> None:
        await self._append_run_event(
            "langchain.chain.end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            data={"outputs": self._jsonable(outputs)},
            tags=tags,
        )

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        **_: Any,
    ) -> None:
        await self._append_error_event(
            "langchain.chain.error",
            error,
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id is not None else None,
            tags=tags,
        )

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        await self._append_run_event(
            "langchain.chat_model.start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            data={
                "name": self._serialized_name(serialized),
                "messages": self._jsonable(messages),
            },
            tags=tags,
            metadata=metadata,
        )

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        await self._append_run_event(
            "langchain.llm.start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            data={
                "name": self._serialized_name(serialized),
                "prompts": self._jsonable(prompts),
            },
            tags=tags,
            metadata=metadata,
        )

    async def on_llm_end(
        self,
        response: Any,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        **_: Any,
    ) -> None:
        await self._append_run_event(
            "langchain.llm.end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            data={"response": self._jsonable(response)},
            tags=tags,
        )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        **_: Any,
    ) -> None:
        await self._append_error_event(
            "langchain.llm.error",
            error,
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id is not None else None,
            tags=tags,
        )

    async def on_custom_event(
        self,
        name: str,
        data: Any,
        *,
        run_id: Any,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        await self._append_run_event(
            f"langchain.custom.{name}",
            run_id=run_id,
            data={"data": self._jsonable(data)},
            tags=tags,
            metadata=metadata,
        )
