from __future__ import annotations

import asyncio

import bubseek_langchain.tools as langchain_tools_module
import pytest
from bubseek_langchain.errors import LangchainConfigError
from bubseek_langchain.tools import bub_registry_to_langchain_tools, bub_tool_to_langchain
from langchain_core.utils.function_calling import convert_to_openai_tool
from republic import Tool, ToolContext


def test_bub_tool_to_langchain_preserves_nested_json_schema() -> None:
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
            },
            "filters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["and", "or"],
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
                "required": ["mode", "tags"],
                "additionalProperties": False,
            },
        },
        "required": ["query", "filters"],
        "additionalProperties": False,
    }
    bub_tool = Tool(
        name="search-docs",
        description="Search docs",
        parameters=parameters,
        handler=lambda **kwargs: kwargs,
    )

    langchain_tool = bub_tool_to_langchain(
        bub_tool,
        tool_context=ToolContext(tape=None, run_id="run-1", state={}),
    )

    assert isinstance(langchain_tool.args_schema, dict)
    assert langchain_tool.tool_call_schema["properties"]["filters"]["properties"]["mode"]["enum"] == ["and", "or"]
    assert langchain_tool.tool_call_schema["properties"]["filters"]["properties"]["tags"]["items"] == {"type": "string"}


def test_bub_tool_to_langchain_passes_context_to_handler() -> None:
    seen: dict[str, object] = {}

    def handler(value: str, *, context: ToolContext) -> str:
        seen["value"] = value
        seen["context"] = context
        return f"ok:{value}"

    bub_tool = Tool(
        name="sample.tool",
        description="Sample tool",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler=handler,
        context=True,
    )
    tool_context = ToolContext(tape="tape-x", run_id="run-1", state={"x": 1})

    langchain_tool = bub_tool_to_langchain(bub_tool, tool_context=tool_context)
    result = asyncio.run(langchain_tool.ainvoke({"value": "hi"}))

    assert result == "ok:hi"
    assert seen == {
        "value": "hi",
        "context": tool_context,
    }


def test_bub_tool_to_langchain_normalizes_nested_defs_schema() -> None:
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "$defs": {
                    "OutgoingMedia": {
                        "type": "object",
                        "properties": {
                            "media_type": {"type": "string", "enum": ["image", "video", "file"]},
                            "file_path": {"type": "string"},
                        },
                        "required": ["media_type", "file_path"],
                    }
                },
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "media": {
                        "anyOf": [
                            {"$ref": "#/$defs/OutgoingMedia"},
                            {"type": "null"},
                        ]
                    },
                },
                "required": ["text"],
            }
        },
        "required": ["message"],
    }
    bub_tool = Tool(
        name="wechat",
        description="Send a WeChat message",
        parameters=parameters,
        handler=lambda **kwargs: kwargs,
    )

    langchain_tool = bub_tool_to_langchain(
        bub_tool,
        tool_context=ToolContext(tape=None, run_id="run-1", state={}),
    )
    openai_tool = convert_to_openai_tool(langchain_tool)

    media_schema = openai_tool["function"]["parameters"]["properties"]["message"]["properties"]["media"]["anyOf"][0]
    assert media_schema["properties"]["media_type"]["enum"] == ["image", "video", "file"]
    assert media_schema["properties"]["file_path"]["type"] == "string"


def test_bub_tool_to_langchain_rejects_non_object_schema() -> None:
    bub_tool = Tool(
        name="bad-schema",
        description="Bad schema tool",
        parameters={"type": "array", "items": {"type": "string"}},
        handler=lambda **kwargs: kwargs,
    )

    with pytest.raises(LangchainConfigError, match="object schema"):
        bub_tool_to_langchain(
            bub_tool,
            tool_context=ToolContext(tape=None, run_id="run-1", state={}),
        )


def test_bub_registry_to_langchain_tools_rejects_name_collisions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        langchain_tools_module,
        "REGISTRY",
        {
            "a-b": Tool(
                name="a-b",
                description="First",
                parameters={},
                handler=lambda **kwargs: kwargs,
            ),
            "a_b": Tool(
                name="a_b",
                description="Second",
                parameters={},
                handler=lambda **kwargs: kwargs,
            ),
        },
    )

    with pytest.raises(LangchainConfigError, match="same LangChain name"):
        bub_registry_to_langchain_tools(
            tool_context=ToolContext(tape=None, run_id="run-1", state={}),
        )
