from __future__ import annotations

from typing import Any, Protocol

from langchain_core.callbacks import AsyncCallbackHandler
from republic import TapeEntry

from .normalize import normalize_langchain_output


class TapeAppender(Protocol):
    async def append_async(self, entry: TapeEntry) -> None: ...


class LangchainTapeCallbackHandler(AsyncCallbackHandler):
    """Append LangChain tool spans to the active Bub tape."""

    def __init__(self, tape: TapeAppender) -> None:
        super().__init__()
        self._tape = tape

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        name = serialized.get("name") or serialized.get("id") or "tool"
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
                parent_run_id=parent_run_id,
                metadata=metadata,
            )
        )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **_: Any,
    ) -> None:
        await self._tape.append_async(
            TapeEntry.tool_result(
                results=[normalize_langchain_output(output)],
                run_id=str(run_id),
                parent_run_id=parent_run_id,
            )
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **_: Any,
    ) -> None:
        await self._tape.append_async(
            TapeEntry.tool_result(
                results=[{"error": str(error)}],
                run_id=str(run_id),
                parent_run_id=parent_run_id,
            )
        )
