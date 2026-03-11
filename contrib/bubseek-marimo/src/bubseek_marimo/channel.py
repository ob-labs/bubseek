"""Marimo channel — WebSocket inbound, insights index embedded."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from pathlib import Path

from bub.channels import Channel
from bub.channels.message import ChannelMessage
from bub.types import MessageHandler
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    host: str = "0.0.0.0"
    port: int = 2718
    workspace: str = ""
    marimo_port: int = 2719
    chat_timeout_seconds: int = 300
    chat_followup_grace_seconds: float = 1.0


class MarimoChannel(Channel):
    """Marimo channel: WebSocket server for gateway dashboard/chat."""

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

        return Path.cwd().resolve()

    def _insights_dir(self) -> Path:
        return self._workspace_dir() / "insights"

    def _render_notebook_template(self, template: str, insights_dir: Path) -> str:
        return (
            template.replace("__BUBSEEK_INSIGHTS_DIR__", repr(str(insights_dir)))
            .replace(
                "__BUBSEEK_CHAT_REQUEST_TIMEOUT_SECONDS__",
                repr(max(self._config.chat_timeout_seconds + 30, 120)),
            )
        )

    _INDEX_TEMPLATE = '''"""Bubseek Insights index — open dashboard or browse notebooks."""
# marimo.App (for directory scanner)
import marimo as mo

app = mo.App()


@app.cell
def _():
    from pathlib import Path

    import marimo as mo

    insights_dir = Path(__BUBSEEK_INSIGHTS_DIR__)
    return insights_dir, mo


@app.cell
def _(insights_dir, mo):
    notebooks = sorted(
        [p for p in insights_dir.glob("*.py") if p.name not in {"dashboard.py", "index.py"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if notebooks:
        lines = [
            "# Bubseek Insights",
            "",
            "- [Open dashboard](/?file=dashboard.py)",
            "- [Open starter visualization example](/?file=example_visualization.py)",
            "",
            "## Notebooks",
        ]
        lines.extend(f"- [{p.stem}](/?file={p.name})" for p in notebooks)
        page = mo.md("\\n".join(lines))
    else:
        page = mo.md(
            "# Bubseek Insights\\n\\n"
            "- [Open dashboard](/?file=dashboard.py)\\n\\n"
            "- [Open starter visualization example](/?file=example_visualization.py)\\n\\n"
            "No insight notebooks yet. Ask Bub in the dashboard to generate one."
        )
    page
    return


if __name__ == "__main__":
    app.run()
'''

    _EXAMPLE_TEMPLATE = '''# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo"]
# ///

"""Example native marimo visualization for Bubseek."""
# marimo.App (for directory scanner)

import marimo as mo

app = mo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    data = [
        {"month": "Jan", "sales": 120, "cost": 75},
        {"month": "Feb", "sales": 145, "cost": 83},
        {"month": "Mar", "sales": 170, "cost": 91},
        {"month": "Apr", "sales": 160, "cost": 95},
        {"month": "May", "sales": 210, "cost": 108},
        {"month": "Jun", "sales": 235, "cost": 120},
    ]
    return data, mo


@app.cell
def _(mo):
    metric = mo.ui.dropdown(
        options={"Sales": "sales", "Cost": "cost"},
        value="Sales",
        label="Metric",
    )
    scale = mo.ui.slider(0.6, 1.6, value=1.0, step=0.1, label="Scale")
    controls = mo.hstack([metric, scale], widths=[0.5, 0.5], align="end")
    controls
    return metric, scale


@app.cell
def _(mo):
    mo.md("# Example Visualization")
    mo.md("A native marimo example using widgets, reactivity, markdown, and SVG rendering.")
    return


@app.cell
def _(data, metric, mo, scale):
    selected = metric.value
    factor = scale.value
    max_value = max(row[selected] for row in data) or 1

    bars = []
    y = 30
    for row in data:
        value = row[selected]
        width = int((value / max_value) * 280 * factor)
        bars.append(
            f"""
            <text x="10" y="{y}" font-size="13" fill="#334155">{row['month']}</text>
            <rect x="72" y="{y - 14}" rx="6" ry="6" width="{width}" height="20" fill="#2563eb"></rect>
            <text x="{82 + width}" y="{y}" font-size="12" fill="#0f172a">{value}</text>
            """
        )
        y += 34

    svg = f"""
    <svg width="420" height="{y}" viewBox="0 0 420 {y}" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8fafc"></rect>
      {''.join(bars)}
    </svg>
    """

    summary = mo.md(
        f"### Summary\\n"
        f"- Selected metric: **{selected}**\\n"
        f"- Latest value: **{data[-1][selected]}**\\n"
        f"- Peak value: **{max_value}**"
    )
    chart = mo.Html(svg)
    mo.vstack([summary, chart], gap=0.75)
    return


if __name__ == "__main__":
    app.run()
'''

    def _ensure_dashboard(self) -> None:
        """Create dashboard.py in insights/ — chat + index, native marimo."""
        from bubseek_marimo.dashboard import DASHBOARD_TEMPLATE

        d = self._insights_dir()
        d.mkdir(parents=True, exist_ok=True)
        dashboard = d / "dashboard.py"
        dashboard.write_text(self._render_notebook_template(DASHBOARD_TEMPLATE, d), encoding="utf-8")
        logger.info("Ensured insights/dashboard.py")

    def _ensure_index(self) -> None:
        """Create index.py in insights/ — placeholder linking to dashboard."""
        d = self._insights_dir()
        if not d.exists():
            return
        index = d / "index.py"
        index.write_text(self._render_notebook_template(self._INDEX_TEMPLATE, d), encoding="utf-8")
        logger.info("Ensured insights/index.py")

    def _ensure_example(self) -> None:
        """Create a native marimo example notebook for the insights index."""
        d = self._insights_dir()
        if not d.exists():
            return
        example = d / "example_visualization.py"
        example.write_text(self._render_notebook_template(self._EXAMPLE_TEMPLATE, d), encoding="utf-8")
        logger.info("Ensured insights/example_visualization.py")

    def _start_marimo(self) -> None:
        """Start marimo run insights/ — dashboard is main entry, gallery for others."""
        d = self._insights_dir()
        if not d.exists():
            return
        try:
            self._marimo_proc = subprocess.Popen(
                ["marimo", "run", str(d), "--port", str(self._config.marimo_port), "--host", "127.0.0.1"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=str(d.parent),
            )
            logger.info("Marimo at http://127.0.0.1:{}/", self._config.marimo_port)
        except Exception as e:
            logger.warning("Could not start marimo: {}", e)

    async def start(self, stop_event: asyncio.Event) -> None:
        """Start WebSocket server and embedded marimo index."""
        self._stop_event = stop_event
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            return

        self._ensure_dashboard()
        self._ensure_index()
        self._ensure_example()
        self._start_marimo()

        self._app = web.Application()
        self._app.router.add_post("/api/chat", self._handle_chat_request)
        self._app.router.add_get("/bub-ws", self._handle_websocket)
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            self._app.router.add_route(method, "/{path:.*}", self._handle_marimo_proxy)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._config.host, self._config.port)
        await self._site.start()

        logger.info(
            "Marimo channel at http://{}:{}/ — marimo dashboard (chat + index)",
            self._config.host,
            self._config.port,
        )

    async def stop(self) -> None:
        """Stop Marimo channel."""
        if self._stop_event:
            self._stop_event.set()
        if self._marimo_proc:
            self._marimo_proc.terminate()
            self._marimo_proc.wait(timeout=5)
            self._marimo_proc = None
        async with self._session_lock:
            for ws in self._ws_sessions.values():
                try:
                    await ws.close()
                except Exception:
                    pass
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

    async def _handle_marimo_proxy(self, request: web.Request) -> web.StreamResponse:
        """Proxy /* to marimo (dashboard). /ws handled separately."""
        if not self._marimo_proc:
            return web.Response(text="Marimo not running.", status=503)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._proxy_websocket(request)
        path = request.match_info.get("path", "") or ""
        url = f"http://127.0.0.1:{self._config.marimo_port}/{path}"
        if request.query_string:
            url += "?" + request.query_string
        body = await request.read() if request.has_body else None
        headers = dict(request.headers)
        headers.pop("Host", None)
        async with ClientSession() as session:
            async with session.request(request.method, url, data=body, headers=headers) as resp:
                body = await resp.read()
                h = {k: v for k, v in resp.headers.items() if k.lower() not in ("transfer-encoding", "connection")}
                return web.Response(body=body, status=resp.status, headers=h)

    def _build_channel_message(self, session_id: str, content: str) -> ChannelMessage:
        is_command = content.startswith(",")
        return ChannelMessage(
            session_id=session_id,
            content=content,
            channel=self.name,
            chat_id=session_id.split(":")[-1],
            kind="command" if is_command else "normal",
            is_active=True,
        )

    async def _dispatch_inbound(self, session_id: str, content: str) -> None:
        channel_msg = self._build_channel_message(session_id=session_id, content=content)
        logger.debug("Marimo inbound session_id={} content={}", session_id, content[:80])
        await self._on_receive(channel_msg)

    async def _handle_chat_request(self, request: web.Request) -> web.Response:
        """Handle native marimo chat via HTTP, suitable for widgets/forms."""
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
            first = await asyncio.wait_for(queue.get(), timeout=self._config.chat_timeout_seconds)
            messages.append(first)
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=self._config.chat_followup_grace_seconds)
                except asyncio.TimeoutError:
                    break
                messages.append(item)
        except asyncio.TimeoutError:
            return web.json_response(
                {
                    "session_id": session_id,
                    "messages": [
                        {
                            "content": "Timed out waiting for Bub response.",
                            "kind": "error",
                        }
                    ],
                },
                status=504,
            )

        return web.json_response({"session_id": session_id, "messages": messages})

    async def _proxy_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Proxy WebSocket to marimo for iframe."""
        path = request.match_info.get("path", "") or ""
        ws_url = f"ws://127.0.0.1:{self._config.marimo_port}/{path}"
        if request.query_string:
            ws_url += "?" + request.query_string
        our_ws = web.WebSocketResponse()
        await our_ws.prepare(request)
        async with ClientSession() as session:
            async with session.ws_connect(ws_url) as remote_ws:
                async def fwd_from_remote():
                    async for msg in remote_ws:
                        if msg.type == web.WSMsgType.TEXT:
                            await our_ws.send_str(msg.data)
                        elif msg.type == web.WSMsgType.BINARY:
                            await our_ws.send_bytes(msg.data)
                        elif msg.type == web.WSMsgType.CLOSE:
                            await our_ws.close()
                            break

                async def fwd_from_client():
                    async for msg in our_ws:
                        if msg.type == web.WSMsgType.TEXT:
                            await remote_ws.send_str(msg.data)
                        elif msg.type == web.WSMsgType.BINARY:
                            await remote_ws.send_bytes(msg.data)
                        elif msg.type == web.WSMsgType.CLOSE:
                            await remote_ws.close()
                            break

                await asyncio.gather(
                    asyncio.create_task(fwd_from_remote()),
                    asyncio.create_task(fwd_from_client()),
                )
        return our_ws

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connection for chat."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        session_id = f"marimo:{uuid.uuid4().hex[:12]}"
        async with self._session_lock:
            self._ws_sessions[session_id] = ws

        try:
            async for msg in ws:
                if msg.type in (web.WSMsgType.TEXT, web.WSMsgType.BINARY):
                    try:
                        data = json.loads(msg.data) if isinstance(msg.data, str) else {}
                        content = data.get("content", "").strip() or str(msg.data)
                    except json.JSONDecodeError:
                        content = str(msg.data)

                    if not content:
                        continue

                    await self._dispatch_inbound(session_id=session_id, content=content)
        except Exception as e:
            logger.warning("Marimo WebSocket error: {}", e)
        finally:
            async with self._session_lock:
                self._ws_sessions.pop(session_id, None)
            await ws.close()

        return ws

    async def send(self, message: ChannelMessage) -> None:
        """Send message back to marimo client via WebSocket."""
        content = (message.content or "").strip()
        session_id = message.session_id
        if not content:
            return

        async with self._session_lock:
            ws = self._ws_sessions.get(session_id)
            queue = self._http_sessions.get(session_id)

        if ws is not None and not ws.closed:
            try:
                payload = json.dumps({"content": content, "kind": message.kind})
                await ws.send_str(payload)
                return
            except Exception as e:
                logger.error("Marimo send failed for session_id={} error={}", session_id, e)
                return

        if queue is not None:
            await queue.put({"content": content, "kind": message.kind})
            return

        logger.debug("Marimo send: no active session for {}", session_id)


