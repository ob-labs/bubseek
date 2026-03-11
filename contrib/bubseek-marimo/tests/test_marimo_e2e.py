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
    from bubseek_marimo.channel import MarimoChannel

    marimo_workspace = tmp_path / "marimo-workspace"
    bubb_workspace = tmp_path / "bub-workspace"
    monkeypatch.setenv("BUB_MARIMO_WORKSPACE", str(marimo_workspace))
    monkeypatch.setenv("BUB_WORKSPACE_PATH", str(bubb_workspace))

    channel = MarimoChannel(_noop_handler)

    assert channel._workspace_dir() == marimo_workspace.resolve()
    assert channel._insights_dir() == marimo_workspace.resolve() / "insights"


def test_workspace_resolution_falls_back_to_cwd(monkeypatch, tmp_path) -> None:
    from bubseek_marimo.channel import MarimoChannel

    monkeypatch.delenv("BUB_MARIMO_WORKSPACE", raising=False)
    monkeypatch.delenv("BUB_WORKSPACE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    channel = MarimoChannel(_noop_handler)

    assert channel._workspace_dir() == tmp_path.resolve()
    assert channel._insights_dir() == tmp_path.resolve() / "insights"


def test_example_template_contains_scanner_markers() -> None:
    from bubseek_marimo.notebooks import EXAMPLE_NOTEBOOK

    assert "import marimo" in EXAMPLE_NOTEBOOK
    assert "marimo.App" in EXAMPLE_NOTEBOOK


@pytest.fixture(scope="module")
def gateway_process():
    """Start gateway with marimo channel, yield process, cleanup on teardown."""
    global PORT, MARIMO_PORT

    workspace = REPO_ROOT
    env = os.environ.copy()
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
        [uv_executable, "run", "bubseek", "gateway", "--enable-channel", "marimo"],
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
    assert "marimo-filename" in body or "dashboard" in body.lower()


def test_index_loads(gateway_process) -> None:
    """Index page loads without internal error (index.py created by channel)."""
    _assert_notebook_loads("index.py")


def test_example_notebook_loads(gateway_process) -> None:
    """Starter example notebook loads from the canonical insights directory."""
    example_path = REPO_ROOT / "insights" / "example_visualization.py"
    assert example_path.exists(), f"Expected generated example at {example_path}"
    _assert_notebook_loads("example_visualization.py")


def test_chat_api_roundtrip(gateway_process) -> None:
    """Native marimo chat endpoint returns agent responses."""
    if not AIOHTTP_AVAILABLE:
        pytest.skip("aiohttp not installed")

    async def _run() -> None:
        async with ClientSession() as session:
            try:
                async with session.post(
                    f"http://127.0.0.1:{PORT}/api/chat",
                    json={"content": "hello"},
                    timeout=30,
                ) as resp:
                    assert resp.status == 200, await resp.text()
                    data = await resp.json()
            except (ClientConnectorError, ClientError) as e:
                pytest.fail(f"Chat API request failed: {e}")

        assert data.get("session_id")
        messages = [m.get("content", "") for m in data.get("messages", []) if m.get("content")]
        assert messages, f"No response from agent. Payload: {data}"

    asyncio.run(_run())
