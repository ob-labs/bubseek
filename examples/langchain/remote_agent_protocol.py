from __future__ import annotations

from bubseek_langchain import AgentProtocolRunnable, RunnableBinding, load_agent_protocol_settings
from bubseek_langchain.bridge import LangchainFactoryRequest


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
    )
