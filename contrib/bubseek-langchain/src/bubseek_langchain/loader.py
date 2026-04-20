from __future__ import annotations

import inspect
from dataclasses import replace
from importlib import import_module
from typing import Any

from .bridge import LangchainFactoryRequest, RunnableBinding
from .errors import LangchainConfigError
from .normalize import normalize_langchain_output


def _factory_error(factory: str, message: str) -> LangchainConfigError:
    return LangchainConfigError(f"{message} (BUB_LANGCHAIN_FACTORY={factory!r})")


def import_object(spec: str) -> Any:
    if ":" not in spec:
        raise _factory_error(spec, "Expected 'module:attr'")
    module_name, attr_name = spec.split(":", 1)
    try:
        module = import_module(module_name)
    except Exception as exc:
        raise _factory_error(spec, f"Failed to import module {module_name!r}: {exc}") from exc
    try:
        return getattr(module, attr_name)
    except AttributeError as exc:
        raise _factory_error(spec, f"Attribute {attr_name!r} not found in module {module_name!r}") from exc


def _is_runnable_like(obj: object) -> bool:
    return hasattr(obj, "invoke") and hasattr(obj, "ainvoke")


def _is_factory_callable(obj: object) -> bool:
    return callable(obj) and not _is_runnable_like(obj) and not isinstance(obj, RunnableBinding)


def _ensure_request_factory(factory: Any, *, factory_spec: str) -> None:
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return
    parameters = signature.parameters
    request_parameter = parameters.get("request")
    if request_parameter is None:
        raise _factory_error(factory_spec, "Factory must accept a `request` keyword argument")
    if request_parameter.kind not in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    ):
        raise _factory_error(factory_spec, "Factory `request` parameter must accept keyword binding")


def ensure_runnable(obj: Any, *, factory: str) -> Any:
    if not _is_runnable_like(obj):
        raise _factory_error(factory, f"Expected a Runnable with invoke/ainvoke, got {type(obj)!r}")
    return obj


def _normalize_factory_result(value: Any, *, factory: str) -> RunnableBinding:
    if not isinstance(value, RunnableBinding):
        raise _factory_error(factory, "Factory must return RunnableBinding")

    ensure_runnable(value.runnable, factory=factory)

    if value.output_parser is None:
        return replace(value, output_parser=normalize_langchain_output)

    if not callable(value.output_parser):
        raise _factory_error(factory, f"Expected output parser to be callable, got {type(value.output_parser)!r}")

    return value


def resolve_runnable_binding(factory: str, request: LangchainFactoryRequest) -> RunnableBinding:
    imported = import_object(factory)
    if not _is_factory_callable(imported):
        raise _factory_error(factory, "BUB_LANGCHAIN_FACTORY must point to a callable factory")
    _ensure_request_factory(imported, factory_spec=factory)
    value = imported(request=request)
    return _normalize_factory_result(value, factory=factory)
