from __future__ import annotations

import json
from typing import Any


def _content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_content_to_str(item) for item in content]
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return str(content["text"])
        return _dict_to_str(content)
    return str(content)


def _message_to_str(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is not None:
        return _content_to_str(content)
    return str(message)


def _dict_to_str(data: dict[str, Any]) -> str:
    if "content" in data:
        return _content_to_str(data["content"])
    if isinstance(data.get("messages"), list):
        parts = [normalize_langchain_output(item) for item in data["messages"]]
        return "\n".join(part for part in parts if part)
    return json.dumps(data, ensure_ascii=False, default=str)


def normalize_langchain_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _dict_to_str(value)
    if isinstance(value, list):
        parts = [normalize_langchain_output(item) for item in value]
        return "\n".join(part for part in parts if part)
    if hasattr(value, "content"):
        return _message_to_str(value)
    return str(value)
