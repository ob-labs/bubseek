from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any


def import_object(spec: str) -> Any:
    if ":" not in spec:
        raise ValueError(f"Expected 'module:attr', got {spec!r}")
    module_name, attr_name = spec.split(":", 1)
    module = import_module(module_name)
    try:
        return getattr(module, attr_name)
    except AttributeError as exc:
        raise AttributeError(f"Attribute {attr_name!r} not found in module {module_name!r}") from exc


def _is_runnable_like(obj: object) -> bool:
    return hasattr(obj, "invoke") and hasattr(obj, "ainvoke")


def _call_with_supported_kwargs(factory: Any, factory_kwargs: dict[str, Any]) -> Any:
    signature = inspect.signature(factory)
    parameters = signature.parameters
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return factory(**factory_kwargs)
    supported_kwargs = {name: value for name, value in factory_kwargs.items() if name in parameters}
    return factory(**supported_kwargs)


def ensure_runnable(obj: Any) -> Any:
    if not _is_runnable_like(obj):
        raise TypeError(f"Expected a Runnable with invoke/ainvoke, got {type(obj)!r}")
    return obj


def _normalize_factory_result(
    value: Any,
    *,
    factory: str,
    factory_kwargs: dict[str, Any],
    default_input: Any,
) -> tuple[Any, Any]:
    if _is_runnable_like(value):
        return ensure_runnable(value), default_input
    if isinstance(value, tuple) and len(value) == 2:
        runnable, invoke_input = value
        return ensure_runnable(runnable), invoke_input
    if callable(value):
        return _normalize_factory_result(
            _call_with_supported_kwargs(value, factory_kwargs),
            factory=factory,
            factory_kwargs=factory_kwargs,
            default_input=default_input,
        )
    raise TypeError(f"Object from {factory!r} is neither Runnable, callable, nor (Runnable, input)")


def resolve_runnable_and_input(factory: str, factory_kwargs: dict[str, Any], default_input: Any) -> tuple[Any, Any]:
    obj = import_object(factory)
    return _normalize_factory_result(
        obj,
        factory=factory,
        factory_kwargs=factory_kwargs,
        default_input=default_input,
    )
