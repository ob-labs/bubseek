from __future__ import annotations

import inspect
import re
from copy import deepcopy
from typing import Any

from bub.tools import REGISTRY
from langchain_core.utils.json_schema import dereference_refs
from republic import Tool, ToolContext

from .errors import LangchainConfigError


def _sanitize_tool_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _empty_args_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": False}


def _args_schema_from_parameters(tool_name: str, parameters: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        if parameters is None:
            return _empty_args_schema()
        raise LangchainConfigError(f"Tool {tool_name!r} parameters must be a JSON schema object")

    if not parameters:
        return _empty_args_schema()

    schema = _normalize_json_schema(parameters)
    schema_type = schema.get("type")
    if schema_type not in (None, "object"):
        raise LangchainConfigError(f"Tool {tool_name!r} parameters must use an object schema, got {schema_type!r}")

    if schema_type is None:
        schema["type"] = "object"

    properties = schema.get("properties")
    if properties is None:
        schema["properties"] = {}
    elif not isinstance(properties, dict):
        raise LangchainConfigError(f"Tool {tool_name!r} parameters.properties must be a mapping")

    schema.setdefault("additionalProperties", False)
    return schema


def _collect_nested_defs(obj: Any, defs_key: str, collected: dict[str, Any]) -> None:
    if isinstance(obj, dict):
        nested_defs = obj.get(defs_key)
        if isinstance(nested_defs, dict):
            for name, value in nested_defs.items():
                collected.setdefault(name, deepcopy(value))
        for value in obj.values():
            _collect_nested_defs(value, defs_key, collected)
        return
    if isinstance(obj, list):
        for item in obj:
            _collect_nested_defs(item, defs_key, collected)


def _normalize_json_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    schema = deepcopy(parameters)
    for defs_key in ("$defs", "definitions"):
        collected: dict[str, Any] = {}
        _collect_nested_defs(schema, defs_key, collected)
        if collected:
            root_defs = schema.get(defs_key)
            if isinstance(root_defs, dict):
                collected = {**collected, **root_defs}
            schema[defs_key] = collected
    normalized = dereference_refs(schema)
    normalized.pop("$defs", None)
    normalized.pop("definitions", None)
    return normalized


def _build_tool_call_kwargs(
    *,
    bub_tool: Tool,
    tool_context: ToolContext,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    call_kwargs = dict(kwargs)
    if bub_tool.context:
        call_kwargs["context"] = tool_context
    return call_kwargs


def _run_bub_tool(
    *,
    bub_tool: Tool,
    tool_context: ToolContext,
    kwargs: dict[str, Any],
) -> Any:
    return bub_tool.run(**_build_tool_call_kwargs(bub_tool=bub_tool, tool_context=tool_context, kwargs=kwargs))


def bub_tool_to_langchain(
    bub_tool: Tool,
    *,
    tool_context: ToolContext,
    tool_name: str | None = None,
) -> Any:
    from langchain_core.tools import StructuredTool

    langchain_name = tool_name or _sanitize_tool_name(bub_tool.name)

    async def _async_call(**kwargs: Any) -> Any:
        result = _run_bub_tool(bub_tool=bub_tool, tool_context=tool_context, kwargs=kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result

    def _sync_call(**kwargs: Any) -> Any:
        result = _run_bub_tool(bub_tool=bub_tool, tool_context=tool_context, kwargs=kwargs)
        if inspect.isawaitable(result):
            raise TypeError(f"Tool {bub_tool.name!r} returned awaitable in sync path")
        return result

    return StructuredTool.from_function(
        func=_sync_call,
        coroutine=_async_call,
        name=langchain_name,
        description=bub_tool.description or bub_tool.name,
        args_schema=_args_schema_from_parameters(bub_tool.name, bub_tool.parameters),
    )


def bub_registry_to_langchain_tools(
    *,
    tool_context: ToolContext,
    include_names: set[str] | None = None,
) -> list[Any]:
    results: list[Any] = []
    seen_names: dict[str, str] = {}
    for name, bub_tool in REGISTRY.items():
        if include_names is not None and name not in include_names:
            continue
        langchain_name = _sanitize_tool_name(bub_tool.name)
        if existing_name := seen_names.get(langchain_name):
            raise LangchainConfigError(
                f"Tools {existing_name!r} and {bub_tool.name!r} map to the same LangChain name {langchain_name!r}"
            )
        seen_names[langchain_name] = bub_tool.name
        results.append(bub_tool_to_langchain(bub_tool, tool_context=tool_context, tool_name=langchain_name))
    return results
