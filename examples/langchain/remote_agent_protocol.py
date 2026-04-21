from __future__ import annotations

import json
from typing import Any

from bubseek_langchain import AgentProtocolRunnable, RunnableBinding, load_agent_protocol_settings
from bubseek_langchain.bridge import LangchainFactoryRequest
from bubseek_langchain.normalize import normalize_langchain_output


def _extract_visible_text_blocks(payload: Any) -> str:
    if isinstance(payload, dict):
        text = payload.get("text")
        return text if isinstance(text, str) else ""
    if not isinstance(payload, list):
        return ""

    parts = [
        text
        for item in payload
        if isinstance(item, dict) and isinstance((text := item.get("text")), str) and text.strip()
    ]
    return "\n".join(parts)


def _parse_remote_agent_output(value: Any) -> str:
    text = normalize_langchain_output(value)
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return text

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return text

    visible_text = _extract_visible_text_blocks(payload)
    return visible_text or text


def remote_agent_protocol_agent(
    *,
    request: LangchainFactoryRequest,
) -> RunnableBinding:
    """Build a RunnableBinding backed by a remote agent-protocol server."""

    runnable = AgentProtocolRunnable(
        settings=load_agent_protocol_settings(),
        session_id=request.session_id,
        langchain_context=request.langchain_context,
    )
    return RunnableBinding(
        runnable=runnable,
        invoke_input=request.prompt,
        output_parser=_parse_remote_agent_output,
    )
