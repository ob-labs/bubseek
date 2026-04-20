from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest
from bubseek_langchain.bridge import LangchainFactoryRequest, LangchainRunContext
from bubseek_langchain.errors import LangchainConfigError
from bubseek_langchain.loader import resolve_runnable_binding

pytest.importorskip("langchain_core")


def _write_module(tmp_path: Path, module_name: str, source: str) -> None:
    (tmp_path / f"{module_name}.py").write_text(textwrap.dedent(source), encoding="utf-8")
    sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def _request(tmp_path: Path, prompt: str = "binding works") -> LangchainFactoryRequest:
    return LangchainFactoryRequest(
        state={},
        session_id="session-1",
        workspace=tmp_path,
        tools=[],
        system_prompt="system prompt",
        prompt=prompt,
        langchain_context=LangchainRunContext(
            session_id="session-1",
            tape_name=None,
            run_id="langchain-run-1",
        ),
    )


def test_resolve_runnable_binding_wraps_missing_module_error() -> None:
    with pytest.raises(LangchainConfigError, match="BUB_LANGCHAIN_FACTORY"):
        resolve_runnable_binding("missing_langchain_factory:factory", _request(Path(".")))


def test_resolve_runnable_binding_accepts_explicit_output_parser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(
        tmp_path,
        "lc_binding_factory",
        """
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        def parse_output(payload):
            return payload["answer"].upper()

        def factory(*, request):
            runnable = RunnableLambda(lambda _: {"answer": request.prompt_text})
            return RunnableBinding(runnable=runnable, invoke_input=None, output_parser=parse_output)
        """,
    )

    binding = resolve_runnable_binding(
        "lc_binding_factory:factory",
        _request(tmp_path),
    )

    assert binding.output_parser is not None
    assert binding.output_parser({"answer": "ok"}) == "OK"


def test_resolve_runnable_binding_rejects_non_binding_return(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(
        tmp_path,
        "lc_non_binding_factory",
        """
        from langchain_core.runnables import RunnableLambda

        def factory(*, request):
            return RunnableLambda(lambda x: x)
        """,
    )

    with pytest.raises(LangchainConfigError, match="Factory must return RunnableBinding"):
        resolve_runnable_binding("lc_non_binding_factory:factory", _request(tmp_path))


def test_resolve_runnable_binding_requires_callable_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(
        tmp_path,
        "lc_binding_value",
        """
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        binding = RunnableBinding(
            runnable=RunnableLambda(lambda x: x),
            invoke_input="hello",
        )
        """,
    )

    with pytest.raises(LangchainConfigError, match="callable factory"):
        resolve_runnable_binding("lc_binding_value:binding", _request(tmp_path))


def test_resolve_runnable_binding_requires_request_keyword(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(
        tmp_path,
        "lc_missing_request_factory",
        """
        from bubseek_langchain import RunnableBinding
        from langchain_core.runnables import RunnableLambda

        def factory(**kwargs):
            return RunnableBinding(runnable=RunnableLambda(lambda x: x), invoke_input=kwargs["request"].prompt_text)
        """,
    )

    with pytest.raises(LangchainConfigError, match=r"`request` keyword argument"):
        resolve_runnable_binding("lc_missing_request_factory:factory", _request(tmp_path))
