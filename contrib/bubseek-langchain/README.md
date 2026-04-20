# bubseek-langchain

`bubseek-langchain` is an optional Bub plugin that routes `run_model` through a LangChain `Runnable`.

Current scope:

- only `Runnable` mode is supported;
- Bub tools can be bridged into LangChain tools;
- Bub tape recording still works for user / assistant turns and tool spans;
- prompts starting with `,` still fall through to Bub built-in internal commands.

## Install

From the repo root:

```bash
uv sync --extra langchain
```

Or install only the plugin package:

```bash
uv pip install -e contrib/bubseek-langchain
```

If you want the DashScope DeepAgents example too:

```bash
uv pip install -e 'contrib/bubseek-langchain[deepagents]'
```

## Enable

Set:

```bash
export BUB_LANGCHAIN_MODE=runnable
export BUB_LANGCHAIN_FACTORY=examples.langchain.minimal_runnable:minimal_lc_agent
```

Optional flags:

- `BUB_LANGCHAIN_INCLUDE_BUB_TOOLS=true|false` (default `true`)
- `BUB_LANGCHAIN_TAPE=true|false` (default `true`)

## Factory Contract

`BUB_LANGCHAIN_FACTORY` must point to a callable `module:attr`.
The callable must accept a single `request: LangchainFactoryRequest` keyword argument.
The factory must return `RunnableBinding`.

`RunnableBinding.invoke_input` is always explicit.
`RunnableBinding.output_parser` is optional; if omitted, the adapter uses the default LangChain output normalizer.

## Examples

Repository examples live under [examples/langchain/README.md](/home/shangzhuoran.szr/oceanbase/bubseek/examples/langchain/README.md):

- [examples/langchain/minimal_runnable.py](/home/shangzhuoran.szr/oceanbase/bubseek/examples/langchain/minimal_runnable.py)
- [examples/langchain/deepagents_dashscope.py](/home/shangzhuoran.szr/oceanbase/bubseek/examples/langchain/deepagents_dashscope.py)

Typical minimal run:

```bash
export BUB_LANGCHAIN_MODE=runnable
export BUB_LANGCHAIN_FACTORY=examples.langchain.minimal_runnable:minimal_lc_agent
uv run bub run "Summarize this workspace in one sentence."
```
