"""Marimo channel with a generated dashboard and persisted chat sessions."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import uuid
from pathlib import Path

try:
    from bubseek.config import discover_project_root, env_with_workspace_dotenv, resolve_tapestore_url
except ImportError:
    discover_project_root = None  # type: ignore[assignment]
    env_with_workspace_dotenv = None  # type: ignore[assignment]
    resolve_tapestore_url = None  # type: ignore[assignment]  # bubseek not installed

if env_with_workspace_dotenv is None:
    from dotenv import dotenv_values

from bub.channels.base import Channel
from bub.channels.message import ChannelMessage
from bub.types import MessageHandler
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from bubseek_marimo.chat_store import MarimoChatStore, TurnConflictError
from bubseek_marimo.notebooks import ensure_seed_notebooks


def _discover_project_root_fallback(start: Path) -> Path | None:
    """Walk up from start for a directory containing .env (used when bubseek not installed)."""
    for d in [start, *start.parents]:
        if (d / ".env").is_file():
            return d
    return None


try:
    from aiohttp import ClientSession, web
    from aiohttp.client_exceptions import ClientConnectorError

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    ClientSession = None  # type: ignore[misc, assignment]
    ClientConnectorError = OSError  # type: ignore[assignment]


class MarimoConfig(BaseSettings):
    """Marimo channel config."""

    model_config = SettingsConfigDict(
        env_prefix="BUB_MARIMO_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 2718
    workspace: str = ""
    marimo_port: int = 2719
    events_page_size: int = 200
    startup_timeout_seconds: float = 30.0
    proxy_retry_attempts: int = 10
    proxy_retry_delay_seconds: float = 0.2


class MarimoChannel(Channel):
    """Marimo channel: dashboard, notebook gallery, and async chat bridge."""

    name = "marimo"

    def __init__(self, on_receive: MessageHandler) -> None:
        self._on_receive = on_receive
        self._config = MarimoConfig()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._stop_event: asyncio.Event | None = None
        self._marimo_proc: subprocess.Popen | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._store = MarimoChatStore(self._tapestore_url())

    def _workspace_dir(self) -> Path:
        if self._config.workspace:
            return Path(self._config.workspace).resolve()

        workspace = os.environ.get("BUB_WORKSPACE_PATH")
        if workspace:
            return Path(workspace).resolve()

        discover = discover_project_root or _discover_project_root_fallback
        for start in (Path.cwd(), Path(__file__).resolve().parent):
            root = discover(start)
            if root is not None:
                return root
        return Path.cwd().resolve()

    def _insights_dir(self) -> Path:
        return self._workspace_dir() / "insights"

    def _tapestore_url(self) -> str:
        if resolve_tapestore_url is not None:
            url = resolve_tapestore_url(self._workspace_dir())
        else:
            env = env_with_workspace_dotenv(self._workspace_dir()) if env_with_workspace_dotenv else self._marimo_env()
            url = (env.get("BUB_TAPESTORE_SQLALCHEMY_URL") or "").strip()
        if url:
            return url
        raise RuntimeError("BUB_TAPESTORE_SQLALCHEMY_URL is required for the marimo channel")

    def _ensure_seed_notebooks(self) -> None:
        insights_dir = self._insights_dir()
        workspace = self._workspace_dir()
        logger.info(
            "Marimo workspace={} .env={} exists={}",
            workspace,
            workspace / ".env",
            (workspace / ".env").is_file(),
        )
        ensure_seed_notebooks(insights_dir)
        logger.info("Ensured starter notebooks under {}", insights_dir)

    def _marimo_env(self) -> dict[str, str]:
        workspace = self._workspace_dir()
        if env_with_workspace_dotenv is not None:
            env = env_with_workspace_dotenv(workspace)
        else:
            env = dict(os.environ)
            env_file = workspace / ".env"
            if env_file.is_file():
                for key, value in dotenv_values(env_file).items():
                    if isinstance(key, str) and isinstance(value, str):
                        env[key] = value
        env["BUB_WORKSPACE_PATH"] = str(workspace)
        env["BUB_MARIMO_PORT"] = str(self._config.port)
        return env

    def _start_marimo(self) -> None:
        insights_dir = self._insights_dir()
        if not insights_dir.exists():
            return

        marimo_executable = shutil.which("marimo")
        if marimo_executable is None:
            logger.warning("Could not start marimo: executable not found")
            return

        try:
            self._marimo_proc = subprocess.Popen(  # noqa: S603
                [
                    marimo_executable,
                    "run",
                    str(insights_dir),
                    "--watch",
                    "--port",
                    str(self._config.marimo_port),
                    "--host",
                    "127.0.0.1",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=str(insights_dir.parent),
                env=self._marimo_env(),
            )
            logger.info("Marimo at http://127.0.0.1:{}/", self._config.marimo_port)
        except Exception as exc:
            logger.warning("Could not start marimo: {}", exc)

    async def _wait_for_marimo_ready(self) -> None:
        deadline = asyncio.get_running_loop().time() + self._config.startup_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            if self._marimo_proc is not None and self._marimo_proc.poll() is not None:
                stderr = ""
                if self._marimo_proc.stderr is not None:
                    stderr = self._marimo_proc.stderr.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"marimo process exited before becoming ready: {stderr}")
            if await asyncio.to_thread(self._backend_port_ready):
                return
            await asyncio.sleep(0.2)
        raise RuntimeError(f"marimo backend did not become ready on port {self._config.marimo_port}")

    def _backend_port_ready(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect(("127.0.0.1", self._config.marimo_port))
            except OSError:
                return False
            return True

    async def start(self, stop_event: asyncio.Event) -> None:
        self._stop_event = stop_event
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            return

        self._ensure_seed_notebooks()
        self._start_marimo()
        await self._wait_for_marimo_ready()

        self._app = web.Application()
        self._app.router.add_post("/api/chat/submit", self._handle_chat_submit)
        self._app.router.add_get("/api/chat/events", self._handle_chat_events)
        self._app.router.add_get("/api/chat/session", self._handle_chat_session)
        self._app.router.add_post("/api/chat/webhook", self._handle_chat_webhook)
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            self._app.router.add_route(method, "/{path:.*}", self._handle_marimo_proxy)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._config.host, self._config.port)
        await self._site.start()
        logger.info("Marimo channel at http://{}:{}/", self._config.host, self._config.port)

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()

        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        if self._marimo_proc:
            self._marimo_proc.terminate()
            self._marimo_proc.wait(timeout=5)
            self._marimo_proc = None
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._site = None
        self._runner = None
        self._app = None
        await asyncio.to_thread(self._store.shutdown)
        logger.info("Marimo channel stopped")

    async def _handle_marimo_proxy(self, request: web.Request) -> web.StreamResponse:
        if not self._marimo_proc:
            return web.Response(text="Marimo not running.", status=503)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._proxy_websocket(request)

        path = request.match_info.get("path", "") or ""
        url = f"http://127.0.0.1:{self._config.marimo_port}/{path}"
        if request.query_string:
            url += f"?{request.query_string}"

        body = await request.read() if request.has_body else None
        headers = dict(request.headers)
        if request.host:
            headers["Host"] = request.host
        headers.setdefault("X-Forwarded-Host", request.host or "")
        headers.setdefault("X-Forwarded-Proto", "http")

        last_error: Exception | None = None
        for _attempt in range(self._config.proxy_retry_attempts):
            try:
                async with (
                    ClientSession() as session,
                    session.request(request.method, url, data=body, headers=headers) as resp,
                ):
                    response_body = await resp.read()
                    response_headers = {
                        key: value
                        for key, value in resp.headers.items()
                        if key.lower() not in ("transfer-encoding", "connection")
                    }
                    return web.Response(body=response_body, status=resp.status, headers=response_headers)
            except ClientConnectorError as exc:
                last_error = exc
                await asyncio.sleep(self._config.proxy_retry_delay_seconds)
        raise web.HTTPServiceUnavailable(text=f"Marimo backend is not ready: {last_error}")

    def _build_channel_message(self, session_id: str, content: str) -> ChannelMessage:
        return ChannelMessage(
            session_id=session_id,
            content=content,
            channel=self.name,
            chat_id=session_id.split(":")[-1],
            kind="command" if content.startswith(",") else "normal",
            is_active=True,
        )

    async def _dispatch_inbound(self, session_id: str, content: str) -> None:
        channel_message = self._build_channel_message(session_id=session_id, content=content)
        logger.debug("Marimo inbound session_id={} content={}", session_id, content[:80])
        await self._on_receive(channel_message)

    def _track_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _run_turn(self, session_id: str, turn_id: str, content: str) -> None:
        try:
            await asyncio.to_thread(self._store.mark_running, session_id, turn_id)
            await self._dispatch_inbound(session_id=session_id, content=content)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Marimo turn failed session_id={} turn_id={}", session_id, turn_id)
            await asyncio.to_thread(self._store.mark_failed, session_id, turn_id, str(exc))

    async def _handle_chat_submit(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON body"}, status=400)

        content = str(data.get("content", "")).strip()
        if not content:
            return web.json_response({"detail": "Missing content"}, status=400)

        session_id = str(data.get("session_id") or f"marimo:{uuid.uuid4().hex[:12]}")
        turn_id = str(data.get("turn_id") or uuid.uuid4().hex[:12])

        try:
            snapshot, event = await asyncio.to_thread(self._store.begin_turn, session_id, turn_id, content)
        except TurnConflictError as exc:
            return web.json_response({"detail": str(exc), "session_id": session_id}, status=409)

        task = asyncio.create_task(self._run_turn(session_id=session_id, turn_id=turn_id, content=content))
        self._track_task(task)
        return web.json_response({
            "session_id": session_id,
            "turn_id": turn_id,
            "status": snapshot.status,
            "session": snapshot.as_dict(),
            "event": event.as_dict(),
        })

    async def _handle_chat_events(self, request: web.Request) -> web.Response:
        session_id = str(request.query.get("session_id", "")).strip()
        if not session_id:
            return web.json_response({"detail": "Missing session_id"}, status=400)

        after_event_id = int(str(request.query.get("after", "0") or "0"))
        snapshot, events = await asyncio.to_thread(
            self._store.list_events,
            session_id,
            after_event_id,
            self._config.events_page_size,
        )
        return web.json_response({
            "session_id": session_id,
            "session": snapshot.as_dict() if snapshot else None,
            "events": [event.as_dict() for event in events],
        })

    async def _handle_chat_session(self, request: web.Request) -> web.Response:
        session_id = str(request.query.get("session_id", "")).strip()
        if not session_id:
            return web.json_response({"detail": "Missing session_id"}, status=400)
        snapshot = await asyncio.to_thread(self._store.get_session, session_id)
        if snapshot is None:
            return web.json_response({"detail": "Unknown session_id"}, status=404)
        return web.json_response({"session": snapshot.as_dict()})

    async def _handle_chat_webhook(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON body"}, status=400)

        session_id = str(data.get("session_id", "")).strip()
        if not session_id:
            return web.json_response({"detail": "Missing session_id"}, status=400)

        turn_id_raw = data.get("turn_id")
        turn_id = str(turn_id_raw).strip() if turn_id_raw is not None else None
        role = str(data.get("role", "assistant") or "assistant")
        kind = str(data.get("kind", "message") or "message")
        content = str(data.get("content", "") or "")
        status = str(data.get("status", "") or "").strip() or None

        snapshot, event = await asyncio.to_thread(
            self._store.record_webhook,
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            kind=kind,
            content=content,
            status=status,
        )
        return web.json_response({
            "session": snapshot.as_dict() if snapshot else None,
            "event": event.as_dict() if event else None,
        })

    async def _proxy_websocket(self, request: web.Request) -> web.WebSocketResponse:
        path = request.match_info.get("path", "") or ""
        ws_url = f"ws://127.0.0.1:{self._config.marimo_port}/{path}"
        if request.query_string:
            ws_url += f"?{request.query_string}"

        local_ws = web.WebSocketResponse()
        await local_ws.prepare(request)

        ws_headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower()
            not in {
                "host",
                "connection",
                "upgrade",
                "sec-websocket-key",
                "sec-websocket-version",
                "sec-websocket-extensions",
                "sec-websocket-protocol",
            }
        }
        ws_headers["Host"] = f"127.0.0.1:{self._config.marimo_port}"
        subprotocols: list[str] = [
            item.strip() for item in request.headers.get("Sec-WebSocket-Protocol", "").split(",") if item.strip()
        ]

        last_error: Exception | None = None
        for _attempt in range(self._config.proxy_retry_attempts):
            try:
                async with (
                    ClientSession() as session,
                    session.ws_connect(
                        ws_url,
                        headers=ws_headers,
                        protocols=subprotocols,
                    ) as remote_ws,
                ):
                    await asyncio.gather(
                        asyncio.create_task(self._relay_remote_messages(remote_ws, local_ws)),
                        asyncio.create_task(self._relay_client_messages(local_ws, remote_ws)),
                    )
                    return local_ws
            except ClientConnectorError as exc:
                last_error = exc
                await asyncio.sleep(self._config.proxy_retry_delay_seconds)

        await local_ws.close(code=1013, message=f"Marimo backend is not ready: {last_error}".encode())
        return local_ws

    async def _relay_remote_messages(self, remote_ws, local_ws: web.WebSocketResponse) -> None:
        async for message in remote_ws:
            if message.type == web.WSMsgType.TEXT:
                await local_ws.send_str(message.data)
            elif message.type == web.WSMsgType.BINARY:
                await local_ws.send_bytes(message.data)
            elif message.type == web.WSMsgType.CLOSE:
                await local_ws.close()
                break

    async def _relay_client_messages(self, local_ws: web.WebSocketResponse, remote_ws) -> None:
        async for message in local_ws:
            if message.type == web.WSMsgType.TEXT:
                await remote_ws.send_str(message.data)
            elif message.type == web.WSMsgType.BINARY:
                await remote_ws.send_bytes(message.data)
            elif message.type == web.WSMsgType.CLOSE:
                await remote_ws.close()
                break

    async def send(self, message: ChannelMessage) -> None:
        content = (message.content or "").strip()
        if not content:
            return

        turn_id = await asyncio.to_thread(self._store.active_turn_id_for_session, message.session_id)
        await asyncio.to_thread(
            self._store.append_event,
            session_id=message.session_id,
            turn_id=turn_id,
            role="assistant",
            kind=message.kind or "message",
            content=content,
            metadata={"source": "channel"},
        )
        if turn_id is not None:
            await asyncio.to_thread(self._store.mark_completed, message.session_id, turn_id)
