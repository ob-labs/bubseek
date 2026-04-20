from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bub.types import State

OutputParser = Callable[[Any], str]


@dataclass(frozen=True)
class LangchainRunContext:
    session_id: str
    tape_name: str | None
    run_id: str

    def as_logger_extra(self) -> dict[str, str]:
        extra = {
            "session_id": self.session_id,
            "langchain_run_id": self.run_id,
        }
        if self.tape_name:
            extra["tape_name"] = self.tape_name
        return extra

    def as_metadata(self) -> dict[str, str]:
        return self.as_logger_extra()

    def as_tags(self) -> list[str]:
        tags = [
            "bubseek-langchain",
            f"session:{self.session_id}",
            f"langchain-run:{self.run_id}",
        ]
        if self.tape_name:
            tags.append(f"tape:{self.tape_name}")
        return tags


@dataclass(frozen=True)
class LangchainFactoryRequest:
    state: State
    session_id: str
    workspace: Path
    tools: list[Any]
    system_prompt: str
    prompt: str | list[dict[str, Any]]
    langchain_context: LangchainRunContext

    @property
    def prompt_text(self) -> str:
        return extract_prompt_text(self.prompt)


@dataclass(frozen=True)
class RunnableBinding:
    runnable: Any
    invoke_input: Any
    output_parser: OutputParser | None = None


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


def build_runnable_config(
    *,
    langchain_context: LangchainRunContext,
    callbacks: list[Any] | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "metadata": langchain_context.as_metadata(),
        "tags": langchain_context.as_tags(),
        "run_name": "bubseek-langchain",
    }
    if callbacks:
        config["callbacks"] = callbacks
    return config
