from __future__ import annotations

from pathlib import Path
from typing import Any

from bub.types import State


def extract_prompt_text(prompt: str | list[dict[str, Any]]) -> str:
    if isinstance(prompt, str):
        return prompt

    texts: list[str] = []
    for part in prompt:
        if not isinstance(part, dict):
            continue
        if part.get("type") != "text":
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
    return "\n".join(texts).strip()


def build_factory_kwargs(
    *,
    state: State,
    session_id: str,
    workspace: Path,
    tools: list[Any],
    system_prompt: str,
    prompt: str | list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "state": state,
        "session_id": session_id,
        "workspace": workspace,
        "tools": tools,
        "system_prompt": system_prompt,
        "prompt": prompt,
    }
