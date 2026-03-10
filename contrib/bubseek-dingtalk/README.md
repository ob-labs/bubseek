# bubseek-dingtalk

DingTalk (钉钉) channel for Bub using Stream Mode.

## What It Provides

- Bub plugin entry point: `dingtalk`
- WebSocket Stream Mode for receiving messages
- HTTP Robot API for sending messages
- Supports private (1:1) and group chats

## Installation

As optional extra:

```bash
uv sync --extra dingtalk
# or
pip install bubseek[dingtalk]
```

From bubseek repo (development):

```bash
uv add ./contrib/bubseek-dingtalk
```

## Configuration

Set these environment variables (or in `.env`):

| Variable | Description |
| --- | --- |
| `BUB_DINGTALK_CLIENT_ID` | AppKey from DingTalk Open Platform |
| `BUB_DINGTALK_CLIENT_SECRET` | AppSecret |
| `BUB_DINGTALK_ALLOW_USERS` | Comma-separated staff_ids to allow, or `*` for all |

## DingTalk App Setup

1. Create an app in [DingTalk Open Platform](https://open.dingtalk.com/)
2. Enable "Robot" capability and "Stream Mode" (流式模式)
3. Configure callback URL if required
4. Use AppKey as `BUB_DINGTALK_CLIENT_ID` and AppSecret as `BUB_DINGTALK_CLIENT_SECRET`
