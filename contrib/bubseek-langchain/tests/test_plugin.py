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

import bubseek_langchain.tools as langchain_tools_module
import pytest
from bubseek_langchain.plugin import LangchainPlugin
from bubseek_langchain.tape_recorder import LangchainTapeCallbackHandler
from langchain_core.callbacks.manager import AsyncCallbackManager
from republic import StreamEvent as RepublicStreamEvent
from republic import TapeContext, TapeEntry, Tool

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
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "")
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
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "")
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
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        calls = []

        async def _run(text, config=None, **kwargs):
            calls.append((text, config))
            return f"ECHO:{text}"

        def factory(*, request):
            assert request.tools == []
            assert request.system_prompt == "system prompt"
            assert request.session_id == "session-1"
            assert request.langchain_context.session_id == "session-1"
            return RunnableBinding(
                runnable=RunnableLambda(lambda x: x, afunc=_run),
                invoke_input=request.prompt_text,
            )
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
    assert config["metadata"]["session_id"] == "session-1"
    assert config["metadata"]["tape_name"] == "tape-x"
    assert "bubseek-langchain" in config["tags"]
    assert len(tape.entries) == 4
    assert [entry.kind for entry in tape.entries] == ["message", "event", "event", "message"]
    assert [entry.payload.get("name") for entry in tape.entries if entry.kind == "event"] == [
        "langchain.chain.start",
        "langchain.chain.end",
    ]
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
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        async def _run(text):
            return f"NO_TAPE:{text}"

        def factory(*, request):
            return RunnableBinding(
                runnable=RunnableLambda(lambda x: x, afunc=_run),
                invoke_input=request.prompt_text,
            )
        """,
    )

    plugin = LangchainPlugin(_Framework())
    result = asyncio.run(plugin.run_model("hello", session_id="session-2", state={}))

    assert result == "NO_TAPE:hello"


def test_include_bub_tools_passes_registry_tools_to_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_with_tools:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "true")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "false")
    monkeypatch.setattr(
        langchain_tools_module,
        "REGISTRY",
        {
            "sample.tool": Tool(
                name="sample.tool",
                description="Sample tool",
                parameters={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler=lambda value: f"ok:{value}",
            ),
            "context.tool": Tool(
                name="context.tool",
                description="Context tool",
                parameters={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler=lambda value, *, context: f"{context.run_id}:{value}",
                context=True,
            ),
        },
    )

    _write_module(
        tmp_path,
        "lc_with_tools",
        """
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        seen = {}

        async def _run(text):
            return f"TOOLS:{text}"

        def factory(*, request):
            seen["tool_names"] = [tool.name for tool in request.tools]
            seen["tool_count"] = len(request.tools)
            seen["schemas"] = [tool.args_schema for tool in request.tools]
            return RunnableBinding(
                runnable=RunnableLambda(lambda x: x, afunc=_run),
                invoke_input=request.prompt_text,
            )
        """,
    )

    plugin = LangchainPlugin(_Framework())
    result = asyncio.run(plugin.run_model("hello", session_id="session-tools", state={}))

    module = _import_module("lc_with_tools")
    assert result == "TOOLS:hello"
    assert module.seen["tool_count"] == 2
    assert module.seen["tool_names"] == ["sample_tool", "context_tool"]
    assert module.seen["schemas"][0]["properties"]["value"]["type"] == "string"


def test_factory_binding_overrides_invoke_input(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_binding_input_factory:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "false")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "false")

    _write_module(
        tmp_path,
        "lc_binding_input_factory",
        """
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        seen = []

        async def _run(value):
            seen.append(value)
            return f"DICT:{value['text']}"

        def factory(*, request):
            text = "\\n".join(part["text"] for part in request.prompt if part.get("type") == "text")
            return RunnableBinding(
                runnable=RunnableLambda(lambda x: x, afunc=_run),
                invoke_input={"text": text, "raw": request.prompt},
            )
        """,
    )

    plugin = LangchainPlugin(_Framework())
    prompt = [{"type": "text", "text": "hello"}, {"type": "image_url", "image_url": {"url": "data:image/png,..."}}]
    result = asyncio.run(plugin.run_model(prompt, session_id="session-3", state={}))

    module = _import_module("lc_binding_input_factory")
    assert result == "DICT:hello"
    assert module.seen == [{"text": "hello", "raw": prompt}]


def test_runnable_binding_makes_result_selection_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_binding_factory:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "false")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "false")

    _write_module(
        tmp_path,
        "lc_binding_factory",
        """
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        def parse_output(payload):
            return payload["answer"]

        def factory(*, request):
            async def _run(_):
                return {
                    "messages": [{"content": "intermediate"}],
                    "answer": f"BINDING:{request.prompt_text}",
                }

            return RunnableBinding(
                runnable=RunnableLambda(lambda x: x, afunc=_run),
                invoke_input=request.prompt_text,
                output_parser=parse_output,
            )
        """,
    )

    plugin = LangchainPlugin(_Framework())
    result = asyncio.run(plugin.run_model("hello", session_id="session-binding", state={}))

    assert result == "BINDING:hello"


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
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        async def _stream(_text, config=None, **kwargs):
            yield "alpha"
            yield "beta"

        def factory(*, request):
            return RunnableBinding(
                runnable=RunnableLambda(lambda x: x, afunc=_stream),
                invoke_input=request.prompt_text,
            )
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


def test_run_model_stream_falls_back_to_ainvoke_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_fallback_factory:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "false")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "true")

    _write_module(
        tmp_path,
        "lc_fallback_factory",
        """
        from bubseek_langchain import RunnableBinding
        builds = []
        seen_configs = []
        seen_contexts = []

        class PlainRunnable:
            def invoke(self, text, config=None):
                return f"SYNC:{text}"

            async def ainvoke(self, text, config=None):
                seen_configs.append(config)
                callbacks = (config or {}).get("callbacks", [])
                for callback in callbacks:
                    await callback.on_chain_start(
                        {"name": "deep_agent"},
                        {"input": text},
                        run_id="chain-1",
                    )
                for callback in callbacks:
                    await callback.on_tool_start(
                        {"name": "plain_tool"},
                        '{"text": "%s"}' % text,
                        run_id="tool-1",
                        parent_run_id="chain-1",
                    )
                for callback in callbacks:
                    await callback.on_tool_end({"ok": text}, run_id="tool-1", parent_run_id="chain-1")
                for callback in callbacks:
                    await callback.on_chain_end(
                        {"output": text},
                        run_id="chain-1",
                    )
                return f"FALLBACK:{text}"

        def factory(*, request):
            builds.append(request.session_id)
            seen_contexts.append(request.langchain_context)
            return RunnableBinding(
                runnable=PlainRunnable(),
                invoke_input=request.prompt_text,
            )
        """,
    )

    tape = _RecordingTape()
    tapes = _RecordingTapes(tape)
    runtime_agent = SimpleNamespace(tapes=tapes)

    plugin = LangchainPlugin(_Framework())
    stream = asyncio.run(
        plugin.run_model_stream(
            "hello",
            session_id="session-5",
            state={"_runtime_agent": runtime_agent, "_runtime_workspace": str(tmp_path)},
        )
    )

    assert stream is not None
    events = asyncio.run(_collect_events(stream))

    module = _import_module("lc_fallback_factory")
    assert [(event.kind, event.data) for event in events] == [
        ("text", {"delta": "FALLBACK:hello"}),
        ("final", {"text": "FALLBACK:hello", "ok": True}),
    ]
    assert module.builds == ["session-5"]
    assert module.seen_contexts[0].session_id == "session-5"
    assert len(module.seen_configs) == 1
    assert [entry.kind for entry in tape.entries] == [
        "message",
        "event",
        "tool_call",
        "tool_result",
        "event",
        "message",
    ]
    assert [entry.payload.get("name") for entry in tape.entries if entry.kind == "event"] == [
        "langchain.chain.start",
        "langchain.chain.end",
    ]
    assert all(entry.meta["session_id"] == "session-5" for entry in tape.entries[1:5])
    assert all(entry.meta["tape_name"] == "tape-x" for entry in tape.entries[1:5])
    assert module.seen_configs[0]["metadata"]["langchain_run_id"].startswith("langchain-")
    assert tapes.ensure_bootstrap_calls == 1
    assert tapes.merge_back_values == [True]


def test_run_model_stream_uses_ainvoke_when_binding_has_custom_output_parser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("BUB_LANGCHAIN_MODE", "runnable")
    monkeypatch.setenv("BUB_LANGCHAIN_FACTORY", "lc_stream_binding:factory")
    monkeypatch.setenv("BUB_LANGCHAIN_INCLUDE_BUB_TOOLS", "false")
    monkeypatch.setenv("BUB_LANGCHAIN_TAPE", "false")

    _write_module(
        tmp_path,
        "lc_stream_binding",
        """
        from bubseek_langchain import RunnableBinding

        class StatefulRunnable:
            def invoke(self, _input, config=None):
                return {"answer": "SYNC"}

            async def ainvoke(self, _input, config=None):
                return {"answer": "FINAL"}

            async def astream(self, _input, config=None):
                yield {"messages": [{"content": "partial"}]}

        def parse_output(payload):
            return payload["answer"]

        def factory(*, request):
            return RunnableBinding(
                runnable=StatefulRunnable(),
                invoke_input=request.prompt_text,
                output_parser=parse_output,
            )
        """,
    )

    plugin = LangchainPlugin(_Framework())
    stream = asyncio.run(plugin.run_model_stream("hello", session_id="session-stream-binding", state={}))

    assert stream is not None
    events = asyncio.run(_collect_events(stream))
    assert [(event.kind, event.data) for event in events] == [
        ("text", {"delta": "FINAL"}),
        ("final", {"text": "FINAL", "ok": True}),
    ]


def test_tape_recorder_records_tool_error() -> None:
    tape = _RecordingTape()
    handler = LangchainTapeCallbackHandler(
        tape,
        session_id="session-err",
        tape_name="tape-err",
        root_run_id="langchain-root",
    )

    asyncio.run(handler.on_tool_error(RuntimeError("boom"), run_id="run-1"))

    assert len(tape.entries) == 1
    entry = tape.entries[0]
    assert entry.kind == "tool_result"
    assert entry.payload["results"] == [{"error": "boom"}]
    assert entry.meta["session_id"] == "session-err"
    assert entry.meta["tape_name"] == "tape-err"
    assert entry.meta["langchain_run_id"] == "langchain-root"


def test_tape_recorder_normalizes_tool_metadata() -> None:
    tape = _RecordingTape()
    handler = LangchainTapeCallbackHandler(tape, session_id="session-meta")

    asyncio.run(
        handler.on_tool_start(
            {"name": "meta.tool"},
            "{}",
            run_id="run-1",
            metadata={"message": SimpleNamespace(content="hello")},
        )
    )

    assert len(tape.entries) == 1
    entry = tape.entries[0]
    assert entry.kind == "tool_call"
    assert entry.meta["metadata"] == {"message": "hello"}


async def _collect_events(stream) -> list[RepublicStreamEvent]:
    return [event async for event in stream]
