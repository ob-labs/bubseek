from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

from bub.hookspecs import hookimpl
from bub.types import State
from bub.utils import workspace_from_state
from republic import AsyncStreamEvents, StreamEvent, StreamState, TapeEntry, ToolContext

from .bridge import build_factory_kwargs, extract_prompt_text
from .config import is_enabled, load_settings, validate_config
from .loader import resolve_runnable_and_input
from .normalize import normalize_langchain_output
from .tape_recorder import LangchainTapeCallbackHandler
from .tools import bub_registry_to_langchain_tools


class LangchainPlugin:
    """Route Bub ``run_model`` through a LangChain Runnable."""

    def __init__(self, framework: Any) -> None:
        self.framework = framework

    def _runtime_agent_from_state(self, state: State) -> Any | None:
        return state.get("_runtime_agent")

    def _build_langchain_tools(self, *, state: State, tape_name: str | None) -> tuple[list[Any], ToolContext]:
        tool_context = ToolContext(
            tape=tape_name,
            run_id=f"langchain-{uuid4().hex}",
            state=dict(state),
        )
        settings = load_settings()
        if not settings.include_bub_tools:
            return [], tool_context
        return bub_registry_to_langchain_tools(tool_context=tool_context), tool_context

    def _system_prompt(self, prompt: str | list[dict[str, Any]], state: State) -> str:
        return self.framework.get_system_prompt(prompt, state)

    def _build_invoke_input(self, prompt: str | list[dict[str, Any]]) -> Any:
        if isinstance(prompt, str):
            return prompt
        return prompt if prompt else extract_prompt_text(prompt)

    def _resolve_runnable_and_input(
        self,
        *,
        prompt: str | list[dict[str, Any]],
        session_id: str,
        state: State,
        tape_name: str | None,
    ) -> tuple[Any, Any]:
        settings = load_settings()
        langchain_tools, _ = self._build_langchain_tools(state=state, tape_name=tape_name)
        factory_kwargs = build_factory_kwargs(
            state=state,
            session_id=session_id,
            workspace=workspace_from_state(state),
            tools=langchain_tools,
            system_prompt=self._system_prompt(prompt, state),
            prompt=prompt,
        )
        return resolve_runnable_and_input(
            cast(str, settings.factory),
            factory_kwargs,
            self._build_invoke_input(prompt),
        )

    async def _invoke_runnable(
        self,
        *,
        prompt: str | list[dict[str, Any]],
        session_id: str,
        state: State,
        tape_name: str | None,
        session_tape: Any | None,
    ) -> str:
        settings = load_settings()
        prompt_text = extract_prompt_text(prompt)
        runnable, invoke_input = self._resolve_runnable_and_input(
            prompt=prompt,
            session_id=session_id,
            state=state,
            tape_name=tape_name,
        )
        callbacks: list[Any] = []
        if settings.tape and session_tape is not None:
            callbacks.append(LangchainTapeCallbackHandler(session_tape))
            await session_tape.append_async(TapeEntry.message({"role": "user", "content": prompt_text}))

        invoke_kwargs: dict[str, Any] = {}
        if callbacks:
            invoke_kwargs["config"] = {"callbacks": callbacks}

        output = await runnable.ainvoke(invoke_input, **invoke_kwargs)
        normalized = normalize_langchain_output(output)

        if settings.tape and session_tape is not None:
            await session_tape.append_async(TapeEntry.message({"role": "assistant", "content": normalized}))
        return normalized

    async def _stream_runnable(
        self,
        *,
        prompt: str | list[dict[str, Any]],
        session_id: str,
        state: State,
        tape_name: str | None,
        session_tape: Any | None,
    ) -> AsyncStreamEvents:
        settings = load_settings()
        prompt_text = extract_prompt_text(prompt)
        runnable, invoke_input = self._resolve_runnable_and_input(
            prompt=prompt,
            session_id=session_id,
            state=state,
            tape_name=tape_name,
        )

        callbacks: list[Any] = []
        if settings.tape and session_tape is not None:
            callbacks.append(LangchainTapeCallbackHandler(session_tape))

        invoke_kwargs: dict[str, Any] = {}
        if callbacks:
            invoke_kwargs["config"] = {"callbacks": callbacks}

        async def iterator():
            assistant_parts: list[str] = []
            if settings.tape and session_tape is not None:
                await session_tape.append_async(TapeEntry.message({"role": "user", "content": prompt_text}))
            if hasattr(runnable, "astream"):
                async for chunk in runnable.astream(invoke_input, **invoke_kwargs):
                    text = normalize_langchain_output(chunk)
                    if not text:
                        continue
                    assistant_parts.append(text)
                    yield StreamEvent("text", {"delta": text})
            else:
                text = await self._invoke_runnable(
                    prompt=prompt,
                    session_id=session_id,
                    state=state,
                    tape_name=tape_name,
                    session_tape=None,
                )
                assistant_parts.append(text)
                yield StreamEvent("text", {"delta": text})

            final_text = "".join(assistant_parts)
            if settings.tape and session_tape is not None:
                await session_tape.append_async(TapeEntry.message({"role": "assistant", "content": final_text}))
            yield StreamEvent("final", {"text": final_text, "ok": True})

        return AsyncStreamEvents(iterator(), state=StreamState())

    @hookimpl(tryfirst=True)
    async def run_model(self, prompt: str | list[dict[str, Any]], session_id: str, state: State) -> str | None:
        settings = load_settings()
        if not is_enabled(settings):
            return None
        if isinstance(prompt, str) and prompt.strip().startswith(","):
            return None

        validate_config(settings)

        runtime_agent = self._runtime_agent_from_state(state)
        if runtime_agent is None or not settings.tape:
            return await self._invoke_runnable(
                prompt=prompt,
                session_id=session_id,
                state=state,
                tape_name=None,
                session_tape=None,
            )

        workspace = workspace_from_state(state)
        session_tape = runtime_agent.tapes.session_tape(session_id, workspace)
        session_tape.context = replace(session_tape.context, state=state)
        merge_back = not session_id.startswith("temp/")
        async with runtime_agent.tapes.fork_tape(session_tape.name, merge_back=merge_back):
            await runtime_agent.tapes.ensure_bootstrap_anchor(session_tape.name)
            return await self._invoke_runnable(
                prompt=prompt,
                session_id=session_id,
                state=state,
                tape_name=session_tape.name,
                session_tape=session_tape,
            )

    @hookimpl(tryfirst=True)
    async def run_model_stream(
        self,
        prompt: str | list[dict[str, Any]],
        session_id: str,
        state: State,
    ) -> AsyncStreamEvents | None:
        settings = load_settings()
        if not is_enabled(settings):
            return None
        if isinstance(prompt, str) and prompt.strip().startswith(","):
            return None

        validate_config(settings)

        runtime_agent = self._runtime_agent_from_state(state)
        if runtime_agent is None or not settings.tape:
            return await self._stream_runnable(
                prompt=prompt,
                session_id=session_id,
                state=state,
                tape_name=None,
                session_tape=None,
            )

        workspace = workspace_from_state(state)
        session_tape = runtime_agent.tapes.session_tape(session_id, workspace)
        session_tape.context = replace(session_tape.context, state=state)
        merge_back = not session_id.startswith("temp/")

        async def iterator():
            async with runtime_agent.tapes.fork_tape(session_tape.name, merge_back=merge_back):
                await runtime_agent.tapes.ensure_bootstrap_anchor(session_tape.name)
                stream = await self._stream_runnable(
                    prompt=prompt,
                    session_id=session_id,
                    state=state,
                    tape_name=session_tape.name,
                    session_tape=session_tape,
                )
                async for event in stream:
                    yield event

        return AsyncStreamEvents(iterator(), state=StreamState())


main = LangchainPlugin
