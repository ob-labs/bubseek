"""Marimo channel with a generated dashboard and runtime insights directory."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
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

from bub.channels import Channel
from bub.channels.message import ChannelMessage
from bub.types import MessageHandler
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from bubseek_marimo.notebooks import ensure_seed_notebooks


def _discover_project_root_fallback(start: Path) -> Path | None:
    """Walk up from start for a directory containing .env (used when bubseek not installed)."""
    for d in [start, *start.parents]:
        if (d / ".env").is_file():
            return d
    return None


def _write_tapestore_url_into(insights_dir: Path, url: str) -> None:
    """Write tapestore URL to insights/.tapestore-url so notebooks can read it (no HTTP from kernel → avoids deadlock)."""
    path = insights_dir / ".tapestore-url"
    with contextlib.suppress(OSError):
        path.write_text(url.strip(), encoding="utf-8")


try:
    from aiohttp import ClientSession, web

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    ClientSession = None  # type: ignore[misc, assignment]


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
    chat_timeout_seconds: int = 300
    chat_followup_grace_seconds: float = 1.0


class MarimoChannel(Channel):
    """Marimo channel: dashboard, notebook gallery, and chat proxy."""

    name = "marimo"

    def __init__(self, on_receive: MessageHandler) -> None:
        self._on_receive = on_receive
        self._config = MarimoConfig()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._stop_event: asyncio.Event | None = None
        self._ws_sessions: dict[str, web.WebSocketResponse] = {}
        self._http_sessions: dict[str, asyncio.Queue[dict[str, str | None]]] = {}
        self._session_lock = asyncio.Lock()
        self._marimo_proc: subprocess.Popen | None = None

    def _workspace_dir(self) -> Path:
        if self._config.workspace:
            return Path(self._config.workspace).resolve()

        workspace = os.environ.get("BUB_WORKSPACE_PATH")
        if workspace:
            return Path(workspace).resolve()

        # Channel may run inside .venv with cwd not project root: discover project root by .env
        discover = discover_project_root or _discover_project_root_fallback
        for start in (Path.cwd(), Path(__file__).resolve().parent):
            root = discover(start)
            if root is not None:
                return root
        return Path.cwd().resolve()

    def _insights_dir(self) -> Path:
        return self._workspace_dir() / "insights"

    def _tapestore_url(self) -> str:
        """Tapestore URL from single source: bubseek.config.resolve_tapestore_url(workspace)."""
        if resolve_tapestore_url is not None:
            return resolve_tapestore_url(self._workspace_dir())
        # Fallback when bubseek not installed
        env = env_with_workspace_dotenv(self._workspace_dir()) if env_with_workspace_dotenv else self._marimo_env()
        url = (env.get("BUB_TAPESTORE_SQLALCHEMY_URL") or "").strip()
        if url:
            return url
        return f"sqlite+pysqlite:///{Path.home().expanduser() / '.bub' / 'tapes.db'}"

    def _ensure_seed_notebooks(self) -> None:
        insights_dir = self._insights_dir()
        workspace = self._workspace_dir()
        env_path = workspace / ".env"
        url = self._tapestore_url()
        logger.info(
            "Marimo workspace={} .env={} exists={} tapestore=>{}",
            workspace,
            env_path,
            env_path.is_file(),
            "seekdb" if url and ("mysql" in url or "oceanbase" in url) else "sqlite",
        )
        ensure_seed_notebooks(insights_dir)
        _write_tapestore_url_into(insights_dir, url)
        logger.info("Ensured starter notebooks under {}", insights_dir)

    def _marimo_env(self) -> dict[str, str]:
        """Build environment for marimo subprocess: inherit current env and overlay workspace .env (same as pydantic-settings / bubseek)."""
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
        """Start `marimo run` against the active insights directory."""
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

    async def start(self, stop_event: asyncio.Event) -> None:
        """Start the aiohttp proxy and the Marimo dashboard process."""
        self._stop_event = stop_event
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            return

        self._ensure_seed_notebooks()
        self._start_marimo()

        self._app = web.Application()
        self._app.router.add_post("/api/chat", self._handle_chat_request)
        self._app.router.add_get("/api/tapestore-url", self._handle_tapestore_url)
        self._app.router.add_get("/api/tapestore-debug", self._handle_tapestore_debug)
        self._app.router.add_get("/bub-ws", self._handle_websocket)
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            self._app.router.add_route(method, "/{path:.*}", self._handle_marimo_proxy)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._config.host, self._config.port)
        await self._site.start()

        logger.info(
            "Marimo channel at http://{}:{}/",
            self._config.host,
            self._config.port,
        )

    async def stop(self) -> None:
        """Stop the proxy, websocket sessions, and the Marimo subprocess."""
        if self._stop_event:
            self._stop_event.set()
        if self._marimo_proc:
            self._marimo_proc.terminate()
            self._marimo_proc.wait(timeout=5)
            self._marimo_proc = None
        async with self._session_lock:
            for websocket in self._ws_sessions.values():
                with contextlib.suppress(Exception):
                    await websocket.close()
            self._ws_sessions.clear()
            self._http_sessions.clear()
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._site = None
        self._runner = None
        self._app = None
        logger.info("Marimo channel stopped")

    async def _handle_tapestore_url(self, request: web.Request) -> web.Response:
        """Return tapestore URL from workspace config (single source of truth for notebooks)."""
        return web.json_response({"url": self._tapestore_url()})

    async def _handle_tapestore_debug(self, request: web.Request) -> web.Response:
        """Diagnostic: workspace, .env path, tapestore URL (curl http://localhost:2718/api/tapestore-debug)."""
        workspace = self._workspace_dir()
        env_path = workspace / ".env"
        url = self._tapestore_url()
        store = "seekdb" if url and ("mysql" in url or "oceanbase" in url) else "sqlite"
        return web.json_response({
            "workspace": str(workspace),
            "env_path": str(env_path),
            "env_exists": env_path.is_file(),
            "tapestore_url": url[:80] + "..." if len(url) > 80 else url,
            "store": store,
        })

    async def _handle_marimo_proxy(self, request: web.Request) -> web.StreamResponse:
        """Proxy all non-chat HTTP traffic to the Marimo app."""
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
        # Forward client Host so marimo generates WS/API URLs for proxy (2718), not backend (2719) — avoids "kernel not found"
        if request.host:
            headers["Host"] = request.host
        headers.setdefault("X-Forwarded-Host", request.host or "")
        headers.setdefault("X-Forwarded-Proto", "http")

        async with ClientSession() as session, session.request(request.method, url, data=body, headers=headers) as resp:
            response_body = await resp.read()
            response_headers = {
                key: value
                for key, value in resp.headers.items()
                if key.lower() not in ("transfer-encoding", "connection")
            }
            return web.Response(body=response_body, status=resp.status, headers=response_headers)

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

    async def _handle_chat_request(self, request: web.Request) -> web.Response:
        """Handle native Marimo chat via HTTP."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"detail": "Invalid JSON body"}, status=400)

        content = str(data.get("content", "")).strip()
        if not content:
            return web.json_response({"detail": "Missing content"}, status=400)

        session_id = str(data.get("session_id") or f"marimo:{uuid.uuid4().hex[:12]}")
        async with self._session_lock:
            queue = self._http_sessions.setdefault(session_id, asyncio.Queue())

        await self._dispatch_inbound(session_id=session_id, content=content)

        messages: list[dict[str, str | None]] = []
        try:
            first_message = await asyncio.wait_for(queue.get(), timeout=self._config.chat_timeout_seconds)
            messages.append(first_message)
            while True:
                try:
                    follow_up = await asyncio.wait_for(queue.get(), timeout=self._config.chat_followup_grace_seconds)
                except TimeoutError:
                    break
                messages.append(follow_up)
        except TimeoutError:
            return web.json_response(
                {
                    "session_id": session_id,
                    "messages": [{"content": "Timed out waiting for Bub response.", "kind": "error"}],
                },
                status=504,
            )

        return web.json_response({"session_id": session_id, "messages": messages})

    async def _proxy_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Proxy WebSocket traffic to the Marimo app for the embedded UI."""
        path = request.match_info.get("path", "") or ""
        ws_url = f"ws://127.0.0.1:{self._config.marimo_port}/{path}"
        if request.query_string:
            ws_url += f"?{request.query_string}"

        local_ws = web.WebSocketResponse()
        await local_ws.prepare(request)

        # Forward Host so backend matches the same origin as the page (avoids kernel/WS mismatch)
        ws_headers = {"Host": request.host} if request.host else {}
        async with ClientSession() as session, session.ws_connect(ws_url, headers=ws_headers) as remote_ws:
            await asyncio.gather(
                asyncio.create_task(self._relay_remote_messages(remote_ws, local_ws)),
                asyncio.create_task(self._relay_client_messages(local_ws, remote_ws)),
            )
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

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle direct websocket chat sessions."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        session_id = f"marimo:{uuid.uuid4().hex[:12]}"
        async with self._session_lock:
            self._ws_sessions[session_id] = ws

        try:
            async for message in ws:
                if message.type not in (web.WSMsgType.TEXT, web.WSMsgType.BINARY):
                    continue

                try:
                    payload = json.loads(message.data) if isinstance(message.data, str) else {}
                    content = payload.get("content", "").strip() or str(message.data)
                except json.JSONDecodeError:
                    content = str(message.data)

                if content:
                    await self._dispatch_inbound(session_id=session_id, content=content)
        except Exception as exc:
            logger.warning("Marimo WebSocket error: {}", exc)
        finally:
            async with self._session_lock:
                self._ws_sessions.pop(session_id, None)
            await ws.close()

        return ws

    async def send(self, message: ChannelMessage) -> None:
        """Send outbound content back to the active Marimo client."""
        content = (message.content or "").strip()
        if not content:
            return

        session_id = message.session_id
        async with self._session_lock:
            websocket = self._ws_sessions.get(session_id)
            queue = self._http_sessions.get(session_id)

        if websocket is not None and not websocket.closed:
            try:
                payload = json.dumps({"content": content, "kind": message.kind})
                await websocket.send_str(payload)
            except Exception as exc:
                logger.error("Marimo send failed for session_id={} error={}", session_id, exc)
            else:
                return

        if queue is not None:
            await queue.put({"content": content, "kind": message.kind})
            return

        logger.debug("Marimo send: no active session for {}", session_id)
