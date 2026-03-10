"""DingTalk channel adapter using Stream Mode."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

from bub.channels import Channel
from bub.channels.message import ChannelMessage
from bub.types import MessageHandler
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from dingtalk_stream import (
        AckMessage,
        CallbackHandler,
        CallbackMessage,
        Credential,
        DingTalkStreamClient,
    )
    from dingtalk_stream.chatbot import ChatbotMessage

    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    CallbackHandler = object  # type: ignore[assignment,misc]
    CallbackMessage = None  # type: ignore[assignment,misc]
    AckMessage = None  # type: ignore[assignment,misc]
    ChatbotMessage = None  # type: ignore[assignment,misc]

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]


class DingTalkConfig(BaseSettings):
    """DingTalk channel config."""

    model_config = SettingsConfigDict(
        env_prefix="BUB_DINGTALK_",
        env_file=".env",
        extra="ignore",
    )

    client_id: str = ""
    client_secret: str = ""
    allow_users: str = ""  # Comma-separated staff_ids, or "*" for all


def _parse_allow_users(value: str) -> set[str]:
    if not value or not value.strip():
        return set()
    v = value.strip()
    if v == "*":
        return {"*"}
    return {u.strip() for u in v.split(",") if u.strip()}


class DingTalkCallbackHandler(CallbackHandler):
    """DingTalk Stream callback handler; forwards messages to Bub."""

    def __init__(self, channel: "DingTalkChannel") -> None:
        super().__init__()
        self.channel = channel

    async def process(self, message: CallbackMessage) -> tuple[int, str]:
        """Process incoming stream message."""
        try:
            chatbot_msg = ChatbotMessage.from_dict(message.data)
            content = ""
            if chatbot_msg.text:
                content = (chatbot_msg.text.content or "").strip()
            if not content:
                content = message.data.get("text", {}).get("content", "").strip()

            if not content:
                logger.warning(
                    "DingTalk: empty or unsupported message type: {}",
                    getattr(chatbot_msg, "message_type", "?"),
                )
                return AckMessage.STATUS_OK, "OK"

            sender_id = chatbot_msg.sender_staff_id or chatbot_msg.sender_id or ""
            sender_name = chatbot_msg.sender_nick or "Unknown"
            conversation_type = message.data.get("conversationType")
            conversation_id = (
                message.data.get("conversationId")
                or message.data.get("openConversationId")
            )

            logger.info(
                "DingTalk inbound from {} ({}): {}",
                sender_name,
                sender_id,
                content[:80],
            )

            task = asyncio.create_task(
                self.channel._on_message(
                    content=content,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    conversation_type=conversation_type,
                    conversation_id=conversation_id,
                )
            )
            self.channel._background_tasks.add(task)
            task.add_done_callback(self.channel._background_tasks.discard)

            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.error("DingTalk process error: {}", e)
            return AckMessage.STATUS_OK, "Error"


class DingTalkChannel(Channel):
    """DingTalk channel using Stream Mode (WebSocket receive, HTTP send)."""

    name = "dingtalk"

    def __init__(self, on_receive: MessageHandler) -> None:
        self._on_receive = on_receive
        self._config = DingTalkConfig()
        self._allow_users = _parse_allow_users(self._config.allow_users)
        self._client: Any = None
        self._http: Any = None
        self._access_token: str | None = None
        self._token_expiry: float = 0
        self._background_tasks: set[asyncio.Task] = set()
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._stream_task: asyncio.Task | None = None

    def _is_allowed(self, sender_id: str) -> bool:
        if not self._allow_users:
            return False
        if "*" in self._allow_users:
            return True
        return str(sender_id) in self._allow_users

    async def start(self, stop_event: asyncio.Event) -> None:
        """Start DingTalk Stream client."""
        self._stop_event = stop_event
        if not DINGTALK_AVAILABLE:
            logger.error("dingtalk-stream not installed. Run: pip install dingtalk-stream")
            return
        if not httpx:
            logger.error("httpx not installed")
            return
        if not self._config.client_id or not self._config.client_secret:
            logger.error("DingTalk client_id/client_secret not configured")
            return

        self._main_loop = asyncio.get_running_loop()
        self._http = httpx.AsyncClient()

        credential = Credential(self._config.client_id, self._config.client_secret)
        self._client = DingTalkStreamClient(credential)
        handler = DingTalkCallbackHandler(self)
        self._client.register_callback_handler(ChatbotMessage.TOPIC, handler)

        logger.info("DingTalk channel starting (Stream Mode)")

        async def _run_stream() -> None:
            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    await self._client.start()
                except Exception as e:
                    logger.warning("DingTalk stream error: {}", e)
                if self._stop_event and self._stop_event.is_set():
                    break
                logger.info("DingTalk reconnecting in 5s...")
                await asyncio.sleep(5)

        self._stream_task = asyncio.create_task(_run_stream())

    async def stop(self) -> None:
        """Stop DingTalk channel."""
        if self._stop_event:
            self._stop_event.set()
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        if self._stream_task:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stream_task
            self._stream_task = None
        if self._http:
            await self._http.aclose()
            self._http = None
        self._client = None
        logger.info("DingTalk channel stopped")

    async def _get_access_token(self) -> str | None:
        """Get or refresh access token."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
        data = {
            "appKey": self._config.client_id,
            "appSecret": self._config.client_secret,
        }

        if not self._http:
            return None
        try:
            resp = await self._http.post(url, json=data)
            resp.raise_for_status()
            res_data = resp.json()
            self._access_token = res_data.get("accessToken")
            expire_in = int(res_data.get("expireIn", 7200))
            self._token_expiry = time.time() + expire_in - 60
            return self._access_token
        except Exception as e:
            logger.error("DingTalk token error: {}", e)
            return None

    async def _send_message(
        self, token: str, chat_id: str, msg_key: str, msg_param: dict[str, Any]
    ) -> bool:
        """Send message via DingTalk Robot API."""
        if not self._http:
            return False

        headers = {"x-acs-dingtalk-access-token": token}
        if chat_id.startswith("group:"):
            url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
            payload = {
                "robotCode": self._config.client_id,
                "openConversationId": chat_id[6:],
                "msgKey": msg_key,
                "msgParam": json.dumps(msg_param, ensure_ascii=False),
            }
        else:
            url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
            payload = {
                "robotCode": self._config.client_id,
                "userIds": [chat_id],
                "msgKey": msg_key,
                "msgParam": json.dumps(msg_param, ensure_ascii=False),
            }

        try:
            resp = await self._http.post(url, json=payload, headers=headers)
            body = resp.text
            if resp.status_code != 200:
                logger.error("DingTalk send failed status={} body={}", resp.status_code, body[:300])
                return False
            result = resp.json() if "application/json" in (resp.headers.get("content-type") or "") else {}
            errcode = result.get("errcode")
            if errcode not in (None, 0):
                logger.error("DingTalk send errcode={} body={}", errcode, body[:300])
                return False
            return True
        except Exception as e:
            logger.error("DingTalk send error: {}", e)
            return False

    async def send(self, message: ChannelMessage) -> None:
        """Send message to DingTalk."""
        token = await self._get_access_token()
        if not token:
            return

        chat_id = message.chat_id or ""
        if not chat_id and message.session_id:
            _, _, chat_id = message.session_id.partition(":")
        if not chat_id:
            logger.warning("DingTalk send: no chat_id session_id={}", message.session_id)
            return

        content = (message.content or "").strip()
        if content:
            ok = await self._send_message(
                token,
                chat_id,
                "sampleMarkdown",
                {"text": content, "title": "Bub Reply"},
            )
            if not ok:
                logger.error("DingTalk send failed for chat_id={}", chat_id)

    async def _on_message(
        self,
        content: str,
        sender_id: str,
        sender_name: str,
        conversation_type: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        """Handle incoming message from callback handler."""
        if not self._is_allowed(sender_id):
            logger.warning("DingTalk inbound denied: sender_id={}", sender_id)
            return

        is_group = conversation_type == "2" and conversation_id
        chat_id = f"group:{conversation_id}" if is_group else sender_id
        session_id = f"{self.name}:{chat_id}"

        is_command = content.strip().startswith(",")
        channel_msg = ChannelMessage(
            session_id=session_id,
            content=content,
            channel=self.name,
            chat_id=chat_id,
            kind="command" if is_command else "normal",
            is_active=True,
        )
        logger.debug("DingTalk inbound session_id={} content={}", session_id, content[:50])
        await self._on_receive(channel_msg)
