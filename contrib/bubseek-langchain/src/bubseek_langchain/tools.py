from __future__ import annotations

import inspect
import re
from typing import Any, cast

from bub.tools import REGISTRY
from pydantic import BaseModel, ConfigDict, Field, create_model
from republic import Tool, ToolContext


class _EmptyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _sanitize_model_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _json_schema_to_annotation(schema: dict[str, Any]) -> Any:
    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        non_null = [item for item in any_of if item.get("type") != "null"]
        if len(non_null) == 1:
            return _json_schema_to_annotation(non_null[0]) | None
        return Any

    schema_type = schema.get("type")
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list[Any]
    if schema_type == "object":
        return dict[str, Any]
    return Any


def _args_model_from_parameters(name: str, parameters: dict[str, Any]) -> type[BaseModel]:
    properties = parameters.get("properties")
    if not isinstance(properties, dict) or not properties:
        return _EmptyParams

    required = set(parameters.get("required", []))
    fields: dict[str, tuple[Any, Any]] = {}
    for field_name, schema in properties.items():
        if not isinstance(schema, dict):
            continue
        annotation = _json_schema_to_annotation(schema)
        default = ... if field_name in required else schema.get("default", None)
        fields[field_name] = (
            annotation,
            Field(default=default, description=schema.get("description")),
        )

    if not fields:
        return _EmptyParams

    unsafe_create_model = cast(Any, create_model)
    model = unsafe_create_model(
        f"BubToolArgs_{_sanitize_model_name(name)}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return cast("type[BaseModel]", model)


def bub_tool_to_langchain(bub_tool: Tool, *, tool_context: ToolContext) -> Any:
    from langchain_core.tools import StructuredTool

    async def _async_call(**kwargs: Any) -> Any:
        call_kwargs = dict(kwargs)
        if bub_tool.context:
            call_kwargs["context"] = tool_context
        result = bub_tool.run(**call_kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result

    def _sync_call(**kwargs: Any) -> Any:
        call_kwargs = dict(kwargs)
        if bub_tool.context:
            call_kwargs["context"] = tool_context
        result = bub_tool.run(**call_kwargs)
        if inspect.isawaitable(result):
            raise TypeError(f"Tool {bub_tool.name!r} returned awaitable in sync path")
        return result

    return StructuredTool.from_function(
        func=_sync_call,
        coroutine=_async_call,
        name=_sanitize_model_name(bub_tool.name),
        description=bub_tool.description or bub_tool.name,
        args_schema=_args_model_from_parameters(bub_tool.name, bub_tool.parameters),
    )


def bub_registry_to_langchain_tools(
    *,
    tool_context: ToolContext,
    include_names: set[str] | None = None,
) -> list[Any]:
    results: list[Any] = []
    for name, bub_tool in REGISTRY.items():
        if include_names is not None and name not in include_names:
            continue
        results.append(bub_tool_to_langchain(bub_tool, tool_context=tool_context))
    return results
