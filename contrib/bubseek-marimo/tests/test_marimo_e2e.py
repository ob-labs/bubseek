"""E2E tests for the Marimo channel, starter notebooks, and chat API."""

from __future__ import annotations

import asyncio
import contextlib
import http.client
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

import pytest

try:
    from aiohttp import ClientSession
    from aiohttp.client_exceptions import ClientConnectorError, ClientError

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

REPO_ROOT = Path(__file__).resolve().parents[3]
MARIMO_SRC = REPO_ROOT / "contrib" / "bubseek-marimo" / "src"
if str(MARIMO_SRC) not in sys.path:
    sys.path.insert(0, str(MARIMO_SRC))

PORT = 2718
MARIMO_PORT = 2719
READY_TIMEOUT = 30
REQUEST_TIMEOUT = 10


async def _noop_handler(*_args, **_kwargs) -> None:
    return None


def _stub_bubseek_oceanbase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "bubseek.oceanbase", ModuleType("bubseek.oceanbase"))


def _require_tapestore_url() -> str:
    url = (os.environ.get("BUB_TAPESTORE_SQLALCHEMY_URL") or "").strip()
    if not url:
        pytest.skip("BUB_TAPESTORE_SQLALCHEMY_URL is required for marimo gateway tests")
    return url


def _port_ready(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_ports(timeout: float = READY_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_ready("127.0.0.1", PORT) and _port_ready("127.0.0.1", MARIMO_PORT):
            return True
        time.sleep(0.5)
    return False


def _http_get(url: str) -> tuple[int, str]:
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname is None or parts.port is None:
        return -1, f"Unsupported URL: {url}"

    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=REQUEST_TIMEOUT)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return -1, str(exc)
    finally:
        connection.close()


def _assert_notebook_loads(filename: str) -> tuple[int, str]:
    status, body = _http_get(f"http://127.0.0.1:{PORT}/?file={filename}")
    assert status == 200, f"Expected 200 for {filename}, got {status}: {body[:500]}"
    assert "Static loading of notebook failed" not in body
    assert "Internal Server Error" not in body
    return status, body


def test_workspace_resolution_priority(monkeypatch, tmp_path) -> None:
    _stub_bubseek_oceanbase(monkeypatch)
    from bubseek_marimo.channel import MarimoChannel

    marimo_workspace = tmp_path / "marimo-workspace"
    bubb_workspace = tmp_path / "bub-workspace"
    monkeypatch.setenv("BUB_TAPESTORE_SQLALCHEMY_URL", "mysql+oceanbase://seek:secret@seekdb.example:2881/analytics")
    monkeypatch.setenv("BUB_MARIMO_WORKSPACE", str(marimo_workspace))
    monkeypatch.setenv("BUB_WORKSPACE_PATH", str(bubb_workspace))

    channel = MarimoChannel(_noop_handler)

    assert channel._workspace_dir() == marimo_workspace.resolve()
    assert channel._insights_dir() == marimo_workspace.resolve() / "insights"


def test_workspace_resolution_falls_back_to_cwd(monkeypatch, tmp_path) -> None:
    _stub_bubseek_oceanbase(monkeypatch)
    from bubseek_marimo.channel import MarimoChannel

    monkeypatch.setenv("BUB_TAPESTORE_SQLALCHEMY_URL", "mysql+oceanbase://seek:secret@seekdb.example:2881/analytics")
    monkeypatch.delenv("BUB_MARIMO_WORKSPACE", raising=False)
    monkeypatch.delenv("BUB_WORKSPACE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    # When no env and cwd has no .env, discover finds repo from channel __file__; force fallback to cwd
    monkeypatch.setattr("bubseek_marimo.channel.discover_project_root", lambda start: None)
    monkeypatch.setattr("bubseek_marimo.channel._discover_project_root_fallback", lambda start: None)

    channel = MarimoChannel(_noop_handler)

    assert channel._workspace_dir() == tmp_path.resolve()
    assert channel._insights_dir() == tmp_path.resolve() / "insights"


def test_marimo_channel_requires_explicit_tapestore_url(monkeypatch, tmp_path) -> None:
    _stub_bubseek_oceanbase(monkeypatch)
    from bubseek_marimo.channel import MarimoChannel

    monkeypatch.delenv("BUB_TAPESTORE_SQLALCHEMY_URL", raising=False)
    monkeypatch.delenv("BUB_MARIMO_WORKSPACE", raising=False)
    monkeypatch.delenv("BUB_WORKSPACE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("bubseek_marimo.channel.discover_project_root", lambda start: None)
    monkeypatch.setattr("bubseek_marimo.channel._discover_project_root_fallback", lambda start: None)

    with pytest.raises(RuntimeError, match="BUB_TAPESTORE_SQLALCHEMY_URL is required"):
        MarimoChannel(_noop_handler)


@pytest.fixture(scope="module")
def gateway_process():
    """Start gateway with marimo channel, yield process, cleanup on teardown."""
    global PORT, MARIMO_PORT

    workspace = REPO_ROOT
    env = os.environ.copy()
    env["BUB_TAPESTORE_SQLALCHEMY_URL"] = _require_tapestore_url()
    PORT = _pick_free_port()
    MARIMO_PORT = _pick_free_port()
    while MARIMO_PORT == PORT:
        MARIMO_PORT = _pick_free_port()
    env["BUB_MARIMO_PORT"] = str(PORT)
    env["BUB_MARIMO_MARIMO_PORT"] = str(MARIMO_PORT)
    env["BUB_WORKSPACE_PATH"] = str(workspace)
    env["BUB_RUNTIME_ENABLED"] = "0"
    if shutil.which("marimo") is None:
        pytest.skip("marimo executable is not available in the current environment")
    uv_executable = shutil.which("uv")
    if uv_executable is None:
        pytest.fail("uv executable is required for marimo gateway tests")

    proc = subprocess.Popen(  # noqa: S603
        [uv_executable, "run", "bub", "gateway", "--enable-channel", "marimo"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        if not _wait_for_ports():
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            proc.terminate()
            proc.wait(timeout=5)
            pytest.fail(f"Gateway did not become ready in {READY_TIMEOUT}s. stderr:\n{stderr}")
        yield proc
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()


def test_gallery_loads(gateway_process) -> None:
    """Gallery (root) returns 200 and HTML."""
    status, body = _http_get(f"http://127.0.0.1:{PORT}/")
    assert status == 200, f"Expected 200, got {status}: {body[:500]}"
    assert "marimo" in body.lower() or "<!DOCTYPE" in body
    assert "No marimo apps found" not in body or "dashboard" in body


def test_dashboard_loads(gateway_process) -> None:
    """Dashboard page loads without internal error."""
    _status, body = _assert_notebook_loads("dashboard.py")
    assert "marimo-filename" in body or "async agent control room" in body.lower()


def test_index_loads(gateway_process) -> None:
    """Index page loads without internal error (index.py created by channel)."""
    _assert_notebook_loads("index.py")


def test_chat_api_roundtrip(gateway_process) -> None:
    """Submit a turn, then poll persisted events until assistant output arrives."""
    if not AIOHTTP_AVAILABLE:
        pytest.skip("aiohttp not installed")

    async def _run() -> None:
        async with ClientSession() as session:
            try:
                async with session.post(
                    f"http://127.0.0.1:{PORT}/api/chat/submit",
                    json={"content": "hello"},
                    timeout=10,
                ) as resp:
                    assert resp.status == 200, await resp.text()
                    submit_data = await resp.json()
            except (ClientConnectorError, ClientError) as e:
                pytest.fail(f"Chat submit failed: {e}")

            session_id = submit_data.get("session_id")
            first_event = submit_data.get("event", {})
            assert session_id
            after_event_id = int(first_event.get("event_id", 0))

            events = []
            for _ in range(40):
                async with session.get(
                    f"http://127.0.0.1:{PORT}/api/chat/events",
                    params={"session_id": session_id, "after": after_event_id},
                    timeout=10,
                ) as resp:
                    assert resp.status == 200, await resp.text()
                    poll_data = await resp.json()
                events.extend(poll_data.get("events", []))
                if any(event.get("role") == "assistant" and event.get("content") for event in events):
                    break
                await asyncio.sleep(0.25)

        messages = [
            event.get("content", "") for event in events if event.get("role") == "assistant" and event.get("content")
        ]
        assert messages, f"No assistant events returned. Events: {events}"

    asyncio.run(_run())


def test_webhook_injection_roundtrip(gateway_process) -> None:
    """Webhook writes assistant events into the persisted session transcript."""
    if not AIOHTTP_AVAILABLE:
        pytest.skip("aiohttp not installed")

    async def _run() -> None:
        async with ClientSession() as session:
            async with session.post(
                f"http://127.0.0.1:{PORT}/api/chat/submit",
                json={"content": "create session"},
                timeout=10,
            ) as resp:
                assert resp.status == 200, await resp.text()
                submit_data = await resp.json()

            session_id = submit_data["session_id"]
            turn_id = submit_data["turn_id"]
            after_event_id = int(submit_data["event"]["event_id"])

            async with session.post(
                f"http://127.0.0.1:{PORT}/api/chat/webhook",
                json={
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "role": "assistant",
                    "kind": "message",
                    "content": "webhook injected response",
                },
                timeout=10,
            ) as resp:
                assert resp.status == 200, await resp.text()

            async with session.get(
                f"http://127.0.0.1:{PORT}/api/chat/events",
                params={"session_id": session_id, "after": after_event_id},
                timeout=10,
            ) as resp:
                assert resp.status == 200, await resp.text()
                poll_data = await resp.json()

        assert any(event.get("content") == "webhook injected response" for event in poll_data.get("events", []))

    asyncio.run(_run())
