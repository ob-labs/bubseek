# bubseek-langchain

`bubseek-langchain` is an optional Bub plugin that routes `run_model` through a LangChain `Runnable`.

It is intentionally narrow:

- only `Runnable` mode is supported;
- Bub tools can be bridged into LangChain tools;
- Bub tape recording remains available for user / assistant turns and tool spans;
- prompts starting with `,` still fall through to Bub built-in internal commands.

## Install

From the root workspace:

```bash
uv sync --extra langchain
```

Or install the contrib package directly:

```bash
uv pip install -e contrib/bubseek-langchain
```

## Enable

Set two environment variables:

```bash
export BUB_LANGCHAIN_MODE=runnable
export BUB_LANGCHAIN_FACTORY=bubseek_langchain.examples.minimal_runnable:minimal_lc_agent
```

Optional flags:

- `BUB_LANGCHAIN_INCLUDE_BUB_TOOLS=true|false` (default `true`)
- `BUB_LANGCHAIN_TAPE=true|false` (default `true`)

## Factory Contract

`BUB_LANGCHAIN_FACTORY` must point to a `module:attr`.

It exists so the plugin can assemble a turn-local runnable from Bub runtime inputs instead of hard-coding a single global chain inside the adapter.

The imported object may be:

- a `Runnable` instance; or
- a factory callable returning a `Runnable`; or
- a factory callable returning `(runnable, invoke_input)`.

If the callable accepts them, the adapter injects:

- `state`
- `session_id`
- `workspace`
- `tools`
- `system_prompt`
- `prompt`

If the factory returns only a runnable, the adapter uses the Bub prompt as the default invoke input:

- `str` prompt stays `str`
- multimodal prompt stays `list[dict]`

If you need a different invoke input shape, derive it from `prompt` and return `(runnable, invoke_input)` explicitly.

## Minimal Example

The package ships a minimal example runnable:

```python
from bubseek_langchain.examples.minimal_runnable import minimal_lc_agent
```

It accepts the Bub-bridged tool list and returns a `RunnableLambda`.

## Example

```bash
export BUB_LANGCHAIN_MODE=runnable
export BUB_LANGCHAIN_FACTORY=bubseek_langchain.examples.minimal_runnable:minimal_lc_agent
uv run bub run "Summarize this workspace in one sentence."
```

To expose Bub tools inside the runnable, keep `BUB_LANGCHAIN_INCLUDE_BUB_TOOLS=true`.
