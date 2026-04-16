from __future__ import annotations

import asyncio
import importlib
import sys
import textwrap
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from bubseek_langchain.plugin import LangchainPlugin
from bubseek_langchain.tape_recorder import LangchainTapeCallbackHandler
from langchain_core.callbacks.manager import AsyncCallbackManager
from republic import StreamEvent as RepublicStreamEvent
from republic import TapeContext, TapeEntry

pytest.importorskip("langchain_core")


class _Framework:
    def get_system_prompt(self, prompt: str | list[dict[str, Any]], state: dict[str, Any]) -> str:
        return "system prompt"


@dataclass
class _RecordingTape:
    name: str = "tape-x"
    context: TapeContext = field(default_factory=lambda: TapeContext(state={}))
    entries: list[TapeEntry] = field(default_factory=list)

    async def append_async(self, entry: TapeEntry) -> None:
        self.entries.append(entry)


class _RecordingTapes:
    def __init__(self, tape: _RecordingTape) -> None:
        self._tape = tape
        self.ensure_bootstrap_calls = 0
        self.merge_back_values: list[bool] = []

    def session_tape(self, session_id: str, workspace: Path) -> _RecordingTape:
        return self._tape

    async def ensure_bootstrap_anchor(self, tape_name: str) -> None:
        self.ensure_bootstrap_calls += 1

    @asynccontextmanager
    async def fork_tape(self, tape_name: str, merge_back: bool = True):
        self.merge_back_values.append(merge_back)
        yield


def _write_module(tmp_path: Path, module_name: str, source: str) -> None:
    (tmp_path / f"{module_name}.py").write_text(textwrap.dedent(source), encoding="utf-8")
    sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def _import_module(module_name: str):
    return importlib.import_module(module_name)


def test_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUB_LANGCHAIN_MODE", raising=False)
    plugin = LangchainPlugin(_Framework())

    result = asyncio.run(plugin.run_model("hello", session_id="session-1", state={}))

    assert result is None


def test_comma_command_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "builtins:str")
    plugin = LangchainPlugin(_Framework())

    result = asyncio.run(plugin.run_model(",help", session_id="session-1", state={}))

    assert result is None


def test_runnable_missing_factory_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.delenv("BUB_LANGCHAIN_FACTORY", raising=False)
    plugin = LangchainPlugin(_Framework())

    with pytest.raises(ValueError, match="BUB_LANGCHAIN_FACTORY"):
        asyncio.run(plugin.run_model("hello", session_id="session-1", state={}))


def test_runnable_mode_echo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_inline_factory:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "false")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "true")

    _write_module(
        tmp_path,
        "lc_inline_factory",
        """
        from langchain_core.runnables import RunnableLambda

        calls = []

        async def _run(text, config=None, **kwargs):
            calls.append((text, config))
            return f"ECHO:{text}"

        def factory(*, tools, system_prompt, **kwargs):
            assert tools == []
            assert system_prompt == "system prompt"
            assert kwargs["session_id"] == "session-1"
            return RunnableLambda(lambda x: x, afunc=_run)
        """,
    )

    tape = _RecordingTape()
    tapes = _RecordingTapes(tape)
    runtime_agent = SimpleNamespace(tapes=tapes)

    plugin = LangchainPlugin(_Framework())
    result = asyncio.run(
        plugin.run_model(
            "ping",
            session_id="session-1",
            state={"_runtime_agent": runtime_agent, "_runtime_workspace": str(tmp_path)},
        )
    )

    module = _import_module("lc_inline_factory")
    assert result == "ECHO:ping"
    assert len(module.calls) == 1
    text, config = module.calls[0]
    assert text == "ping"
    assert isinstance(config, dict)
    callbacks = config["callbacks"]
    assert isinstance(callbacks, AsyncCallbackManager)
    assert len(tape.entries) == 2
    assert [entry.kind for entry in tape.entries] == ["message", "message"]
    assert tapes.ensure_bootstrap_calls == 1
    assert tapes.merge_back_values == [True]


def test_missing_runtime_agent_without_tape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_no_tape:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "false")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "false")

    _write_module(
        tmp_path,
        "lc_no_tape",
        """
        from langchain_core.runnables import RunnableLambda

        async def _run(text):
            return f"NO_TAPE:{text}"

        def factory(**kwargs):
            return RunnableLambda(lambda x: x, afunc=_run)
        """,
    )

    plugin = LangchainPlugin(_Framework())
    result = asyncio.run(plugin.run_model("hello", session_id="session-2", state={}))

    assert result == "NO_TAPE:hello"


def test_factory_tuple_overrides_invoke_input(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_tuple_factory:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "false")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "false")

    _write_module(
        tmp_path,
        "lc_tuple_factory",
        """
        from langchain_core.runnables import RunnableLambda

        seen = []

        async def _run(value):
            seen.append(value)
            return f"DICT:{value['text']}"

        def factory(*, prompt, **kwargs):
            text = "\\n".join(part["text"] for part in prompt if part.get("type") == "text")
            return RunnableLambda(lambda x: x, afunc=_run), {"text": text, "raw": prompt}
        """,
    )

    plugin = LangchainPlugin(_Framework())
    prompt = [{"type": "text", "text": "hello"}, {"type": "image_url", "image_url": {"url": "data:image/png,..."}}]
    result = asyncio.run(plugin.run_model(prompt, session_id="session-3", state={}))

    module = _import_module("lc_tuple_factory")
    assert result == "DICT:hello"
    assert module.seen == [{"text": "hello", "raw": prompt}]


def test_run_model_stream_uses_runnable_astream(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_stream_factory:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "false")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "false")

    _write_module(
        tmp_path,
        "lc_stream_factory",
        """
        from langchain_core.runnables import RunnableLambda

        async def _stream(_text, config=None, **kwargs):
            yield "alpha"
            yield "beta"

        def factory(**kwargs):
            return RunnableLambda(lambda x: x, afunc=_stream)
        """,
    )

    plugin = LangchainPlugin(_Framework())
    stream = asyncio.run(plugin.run_model_stream("hello", session_id="session-4", state={}))

    assert stream is not None
    events = asyncio.run(_collect_events(stream))
    assert [(event.kind, event.data) for event in events] == [
        ("text", {"delta": "alpha"}),
        ("text", {"delta": "beta"}),
        ("final", {"text": "alphabeta", "ok": True}),
    ]


def test_tape_recorder_records_tool_error() -> None:
    tape = _RecordingTape()
    handler = LangchainTapeCallbackHandler(tape)

    asyncio.run(handler.on_tool_error(RuntimeError("boom"), run_id="run-1"))

    assert len(tape.entries) == 1
    entry = tape.entries[0]
    assert entry.kind == "tool_result"
    assert entry.payload["results"] == [{"error": "boom"}]


async def _collect_events(stream) -> list[RepublicStreamEvent]:
    return [event async for event in stream]
