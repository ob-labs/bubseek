# LangChain Examples

These are repository-level factories for `bubseek-langchain`.

They are loaded through `BUB_LANGCHAIN_FACTORY`, not imported from the plugin package itself.
Each factory returns `RunnableBinding`.
Each factory accepts `request: LangchainFactoryRequest`.

## Prerequisites

From the repo root:

```bash
uv sync --extra langchain
```

For the DashScope DeepAgents example, install the extra runtime deps if they are not already present:

```bash
uv pip install -e 'contrib/bubseek-langchain[deepagents]'
```

## Minimal Runnable

Factory path:

```bash
examples.langchain.minimal_runnable:minimal_lc_agent
```

Enable it:

```bash
export BUB_LANGCHAIN_MODE=runnable
export BUB_LANGCHAIN_FACTORY=examples.langchain.minimal_runnable:minimal_lc_agent
```

Run it:

```bash
uv run bub chat
uv run bub run "Summarize this workspace in one sentence."
```

## DeepAgents + DashScope

Factory path:

```bash
examples.langchain.deepagents_dashscope:dashscope_deep_agent
```

Enable it:

```bash
export BUB_LANGCHAIN_MODE=runnable
export BUB_LANGCHAIN_FACTORY=examples.langchain.deepagents_dashscope:dashscope_deep_agent
export BUB_MODEL=openai:glm-5.1
export BUB_API_KEY=your-dashscope-api-key
export BUB_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
```

Optional explicit overrides for the example:

```bash
export BUB_DEEPAGENTS_MODEL=glm-5.1
export BUB_DEEPAGENTS_API_KEY=your-dashscope-api-key
export BUB_DEEPAGENTS_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
```

Run it:

```bash
uv run bub chat
uv run bub gateway --enable-channel marimo
```

This example includes:

```python
def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"
```

If `BUB_LANGCHAIN_INCLUDE_BUB_TOOLS=true`, the DeepAgents example also appends Bub-bridged tools to its tool list.

## Remote Agent Protocol

Factory path:

```bash
examples.langchain.remote_agent_protocol:remote_agent_protocol_agent
```

Enable it:

```bash
export BUB_LANGCHAIN_MODE=runnable
export BUB_LANGCHAIN_FACTORY=examples.langchain.remote_agent_protocol:remote_agent_protocol_agent
export BUB_AGENT_PROTOCOL_URL=http://localhost:2024
export BUB_AGENT_PROTOCOL_AGENT_ID=agent
```

Optional override:

```bash
export BUB_AGENT_PROTOCOL_API_KEY=your-api-key
export BUB_AGENT_PROTOCOL_STATEFUL=true
```

Run it:

```bash
uv run bub chat
uv run bub run "Summarize this workspace in one sentence."
```

Notes:

- `BUB_AGENT_PROTOCOL_STATEFUL=true` maps each Bub session to a deterministic protocol `thread_id`.
- The adapter uses `langgraph_sdk.get_client()` as transport, but only relies on the standard `agent_id`, `thread_id`, `messages`, `values`, and `stream_mode` subset.
- Remote tool execution remains owned by the server-side assistant; local Bub tools are not forwarded into the remote runtime.
