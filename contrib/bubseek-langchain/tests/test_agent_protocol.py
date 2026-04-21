from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from bubseek_langchain.agent_protocol import (
    AgentProtocolInterruptedError,
    AgentProtocolRemoteError,
    AgentProtocolRunnable,
    AgentProtocolSettings,
)
from bubseek_langchain.bridge import LangchainRunContext
from langchain_core.runnables import Runnable


class _FakeRunsClient:
    def __init__(self, *, wait_response: Any, stream_parts: list[Any]) -> None:
        self.wait_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self._wait_response = wait_response
        self._stream_parts = list(stream_parts)

    async def wait(self, **kwargs: Any) -> Any:
        self.wait_calls.append(kwargs)
        return self._wait_response

    async def stream(self, **kwargs: Any):
        self.stream_calls.append(kwargs)
        for part in self._stream_parts:
            yield part


class _FakeClient:
    def __init__(self, *, wait_response: Any, stream_parts: list[Any]) -> None:
        self.runs = _FakeRunsClient(wait_response=wait_response, stream_parts=stream_parts)


def _run_context() -> LangchainRunContext:
    return LangchainRunContext(
        session_id="session-1",
        tape_name="tape-x",
        run_id="langchain-run-1",
    )


def test_agent_protocol_runnable_is_langchain_compatible() -> None:
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://example.com", agent_id="agent"),
        session_id="session-1",
        langchain_context=_run_context(),
    )

    assert isinstance(runnable, Runnable)
    assert callable(runnable.invoke)
    assert callable(runnable.ainvoke)
    assert callable(runnable.astream)


def test_ainvoke_uses_deterministic_thread_id_for_stateful_sessions() -> None:
    fake_client = _FakeClient(
        wait_response={"messages": [{"role": "assistant", "content": "remote answer"}]},
        stream_parts=[],
    )
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://remote", agent_id="agent", stateful=True),
        session_id="session-1",
        langchain_context=_run_context(),
    )
    runnable._client = fake_client

    first = asyncio.run(runnable.ainvoke("hello"))
    second = asyncio.run(runnable.ainvoke("again"))

    assert first["messages"][-1]["content"] == "remote answer"
    assert second["messages"][-1]["content"] == "remote answer"
    assert len(fake_client.runs.wait_calls) == 2
    first_call = fake_client.runs.wait_calls[0]
    second_call = fake_client.runs.wait_calls[1]
    assert first_call["assistant_id"] == "agent"
    assert first_call["input"] == {"messages": [{"role": "user", "content": "hello"}]}
    assert first_call["if_not_exists"] == "create"
    assert first_call["thread_id"].startswith("bubseek-")
    assert second_call["thread_id"] == first_call["thread_id"]


def test_ainvoke_passes_dict_input_through() -> None:
    fake_client = _FakeClient(wait_response={"ok": True}, stream_parts=[])
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://remote", agent_id="agent", stateful=False),
        session_id=None,
        langchain_context=_run_context(),
    )
    runnable._client = fake_client

    payload = {"messages": [{"role": "user", "content": "hi"}], "context": {"mode": "fast"}}
    asyncio.run(runnable.ainvoke(payload))

    assert fake_client.runs.wait_calls[0]["thread_id"] is None
    assert fake_client.runs.wait_calls[0]["input"] == payload
    assert fake_client.runs.wait_calls[0]["if_not_exists"] is None


def test_ainvoke_merges_config_metadata() -> None:
    fake_client = _FakeClient(wait_response={"ok": True}, stream_parts=[])
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://remote", agent_id="agent", stateful=False),
        session_id=None,
        langchain_context=_run_context(),
    )
    runnable._client = fake_client

    asyncio.run(runnable.ainvoke("hello", config={"metadata": {"source": "test"}}))

    assert fake_client.runs.wait_calls[0]["metadata"] == {
        "session_id": "session-1",
        "langchain_run_id": "langchain-run-1",
        "tape_name": "tape-x",
        "source": "test",
    }


def test_astream_yields_assistant_message_chunks() -> None:
    fake_client = _FakeClient(
        wait_response=None,
        stream_parts=[
            {"event": "messages/partial", "data": [{"type": "human", "content": "hello"}]},
            {"event": "messages/partial", "data": [{"type": "ai", "content": "Hel"}]},
            {"event": "messages/partial", "data": [{"type": "ai", "content": "lo"}]},
            {"event": "values", "data": {"messages": [{"type": "ai", "content": "Hello"}]}},
        ],
    )
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://remote", agent_id="agent", stateful=False),
        session_id=None,
        langchain_context=_run_context(),
    )
    runnable._client = fake_client

    async def _collect() -> list[str]:
        return [chunk async for chunk in runnable.astream("hello")]

    chunks = asyncio.run(_collect())

    assert chunks == ["Hel", "lo"]
    assert fake_client.runs.stream_calls[0]["stream_mode"] == ["messages", "values", "updates"]
    assert "version" not in fake_client.runs.stream_calls[0]


def test_astream_does_not_duplicate_complete_message_after_partials() -> None:
    fake_client = _FakeClient(
        wait_response=None,
        stream_parts=[
            {"event": "messages/partial", "data": [{"type": "ai", "content": "Hel"}]},
            {"event": "messages/partial", "data": [{"type": "ai", "content": "lo"}]},
            {"event": "messages/complete", "data": [{"type": "ai", "content": "Hello"}]},
        ],
    )
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://remote", agent_id="agent", stateful=False),
        session_id=None,
        langchain_context=_run_context(),
    )
    runnable._client = fake_client

    async def _collect() -> list[str]:
        return [chunk async for chunk in runnable.astream("hello")]

    assert asyncio.run(_collect()) == ["Hel", "lo"]


def test_astream_falls_back_to_final_state_when_no_message_chunks() -> None:
    fake_client = _FakeClient(
        wait_response=None,
        stream_parts=[
            {"event": "values", "data": {"messages": [{"type": "ai", "content": "Final answer"}]}},
        ],
    )
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://remote", agent_id="agent", stateful=False),
        session_id=None,
        langchain_context=_run_context(),
    )
    runnable._client = fake_client

    async def _collect() -> list[str]:
        return [chunk async for chunk in runnable.astream("hello")]

    chunks = asyncio.run(_collect())

    assert chunks == ["Final answer"]


def test_astream_raises_on_remote_error_event() -> None:
    fake_client = _FakeClient(
        wait_response=None,
        stream_parts=[
            {"event": "error", "data": {"message": "boom"}},
        ],
    )
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://remote", agent_id="agent", stateful=False),
        session_id=None,
        langchain_context=_run_context(),
    )
    runnable._client = fake_client

    async def _collect() -> list[str]:
        return [chunk async for chunk in runnable.astream("hello")]

    with pytest.raises(AgentProtocolRemoteError, match="boom"):
        asyncio.run(_collect())


def test_astream_raises_on_interrupt_update_event() -> None:
    fake_client = _FakeClient(
        wait_response=None,
        stream_parts=[
            {"event": "updates", "data": {"__interrupt__": [{"value": "wait"}]}},
        ],
    )
    runnable = AgentProtocolRunnable(
        settings=AgentProtocolSettings(url="http://remote", agent_id="agent", stateful=False),
        session_id=None,
        langchain_context=_run_context(),
    )
    runnable._client = fake_client

    async def _collect() -> list[str]:
        return [chunk async for chunk in runnable.astream("hello")]

    with pytest.raises(AgentProtocolInterruptedError, match="interrupted"):
        asyncio.run(_collect())


def test_remote_example_factory_uses_prompt_and_request_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from bubseek_langchain.bridge import LangchainFactoryRequest

    from examples.langchain.remote_agent_protocol import _parse_remote_agent_output, remote_agent_protocol_agent

    monkeypatch.setenv("BUB_AGENT_PROTOCOL_URL", "http://remote")
    monkeypatch.setenv("BUB_AGENT_PROTOCOL_AGENT_ID", "agent")

    request = LangchainFactoryRequest(
        state={},
        session_id="session-1",
        workspace=tmp_path,
        tools=[],
        system_prompt="system",
        prompt=[{"type": "text", "text": "hello remote"}],
        langchain_context=_run_context(),
    )

    binding = remote_agent_protocol_agent(request=request)

    assert binding.invoke_input == request.prompt
    assert isinstance(binding.runnable, AgentProtocolRunnable)
    assert binding.output_parser is _parse_remote_agent_output


def test_remote_output_parser_extracts_visible_text_blocks() -> None:
    from examples.langchain.remote_agent_protocol import _parse_remote_agent_output

    payload = '[{"signature":"","thinking":"internal","type":"thinking"},{"text":"Visible answer","type":"text"}]'

    assert _parse_remote_agent_output(payload) == "Visible answer"
