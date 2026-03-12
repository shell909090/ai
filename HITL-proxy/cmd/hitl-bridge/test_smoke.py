"""Smoke test: bridge ping against the real hitl-proxy binary."""

import asyncio
import hashlib
import socket
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

import hitl_bridge

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROXY_BIN = PROJECT_ROOT / "bin" / "hitl-proxy"

API_KEY = "test-key"
AGENT_NAME = "smoke-test"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} not ready after {timeout}s")


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


@pytest.fixture()
def proxy_server(tmp_path: Path):
    """Start the real hitl-proxy and yield (url, api_key)."""
    if not PROXY_BIN.exists():
        pytest.skip(f"proxy binary not found: {PROXY_BIN}")

    port = _free_port()
    db_path = tmp_path / "hitl.db"
    cred_file = tmp_path / "credentials.enc"

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"listen: '127.0.0.1:{port}'\n"
        f"database:\n  path: '{db_path}'\n"
        f"cred:\n  file: '{cred_file}'\n"
    )

    env = {"HITL_ADMIN_PASSWORD": "smoke-test-password"}
    proc = subprocess.Popen(
        [str(PROXY_BIN), "--config", str(config_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    try:
        _wait_for_port(port)
    except RuntimeError:
        proc.kill()
        proc.wait()
        raise

    # Insert API key into the DB
    key_hash = hashlib.sha256(API_KEY.encode()).hexdigest()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO api_keys (key_hash, agent_name) VALUES (?, ?)",
        (key_hash, AGENT_NAME),
    )
    conn.commit()
    conn.close()

    url = f"http://127.0.0.1:{port}/mcp/sse"
    yield url, API_KEY

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def test_smoke_ping(proxy_server: tuple[str, str]) -> None:
    """Bridge ping against the real hitl-proxy should succeed."""
    url, api_key = proxy_server
    asyncio.run(hitl_bridge.ping(url, api_key=api_key))
