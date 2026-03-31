
# Getting started

bubseek is an attempt to explore a different approach to enterprise data needs: instead of scheduling BI tickets, tell the agent what you want and get insights back.

## Prerequisites

- **Python 3.12+** — Check with `python3 --version`
- **[uv](https://docs.astral.sh/uv/)** — Install with:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

## Install

```bash
git clone https://github.com/ob-labs/bubseek.git
cd bubseek
uv sync
```

Verify:

```bash
uv run bub --help
```

## Configure model (required)

bubseek needs an LLM API. Choose a provider and get your API key:

### OpenRouter (recommended)

Unified access to many models with a single API key.

1. Visit [https://openrouter.ai/](https://openrouter.ai/) → Sign in
2. Go to [https://openrouter.ai/keys](https://openrouter.ai/keys) → Create Key

```bash
export BUB_MODEL=openrouter:qwen/qwen3-coder-next
export BUB_API_KEY=sk-or-v1-your-key-here
export BUB_API_BASE=https://openrouter.ai/api/v1
```

### OpenAI

1. Visit [https://platform.openai.com/](https://platform.openai.com/) → Sign up
2. Go to [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys) → Create new secret key

```bash
export BUB_MODEL=openai:gpt-4o
export BUB_API_KEY=sk-your-key-here
export BUB_API_BASE=https://api.openai.com/v1
```

### Custom OpenAI-compatible API

For self-hosted models or other providers:

```bash
export BUB_MODEL=openai:your-model-name
export BUB_API_KEY=your-key-here
export BUB_API_BASE=https://your-api-endpoint/v1
```

## Configure database (required for tape storage)

### OceanBase/seekdb

**Deploy with Docker:**

```bash
# Quick start (for testing)
docker run -d -p 2881:2881 oceanbase/seekdb

# With data persistence
mkdir -p seekdb
docker run -d -p 2881:2881 -v $PWD/seekdb:/var/lib/oceanbase --name seekdb oceanbase/seekdb
```

**Connect and create database:**

```bash
mysql -uroot -h127.0.0.1 -P2881 -p
```

```sql
CREATE DATABASE bubseek;
```

**Configure:**

```bash
export BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://root@127.0.0.1:2881/bubseek
```

For detailed deployment options, see [OceanBase Docker deployment guide](https://www.oceanbase.ai/docs/deploy-by-docker).

## Quickstart verification

Run this to verify your setup:

```bash
uv run bub chat
```

You should see the agent start. Try asking: "Hello, what can you do?"

If errors occur, check:
1. API key is correct and has credits
2. Database connection is valid
3. Network connectivity

## Enable channels (optional)

See [Configuration](configuration.md) for channel setup details.

## Next steps

- [Configuration](configuration.md) — Channel credentials, skills, runtime options
- [Architecture](architecture.md) — Design overview
