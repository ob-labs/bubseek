from __future__ import annotations

from bubseek_langchain.bridge import LangchainFactoryRequest, RunnableBinding
from langchain_core.runnables import RunnableLambda


def minimal_lc_agent(
    *,
    request: LangchainFactoryRequest,
) -> RunnableBinding:
    """Return a minimal Runnable showing the single-request factory contract."""

    tool_names = [getattr(tool, "name", "tool") for tool in request.tools]
    prompt_prefix = (
        request.system_prompt.strip().splitlines()[0] if request.system_prompt.strip() else "No system prompt"
    )

    def _run(text: str) -> str:
        summary = f"[minimal_lc_agent] {text.strip()}"
        if tool_names:
            return f"{summary}\nTools: {', '.join(tool_names)}\nSystem: {prompt_prefix}"
        return f"{summary}\nSystem: {prompt_prefix}"

    return RunnableBinding(
        runnable=RunnableLambda(_run),
        invoke_input=request.prompt_text,
    )
