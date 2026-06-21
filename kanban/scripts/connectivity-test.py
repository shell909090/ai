#!/usr/bin/env python3
"""Connectivity smoke test for the kanban scheduler.

Verifies the two external dependencies the scheduler needs at runtime:
  1. Trello REST API (using ?key=&token= simple auth)
  2. opencode serve HTTP API (basic auth)

Output is one JSON line per step plus a SUMMARY line. Exit code is 0
if no step FAILs, 2 if any step FAILs. SKIPPED counts as neither pass
nor fail (the step is reported but the test continues).

A test is SKIPPED (not FAIL) when its required credentials are
absent. This is the expected behaviour when running outside the
operator's normal environment.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def emit(step: str, result: str, detail: str = "") -> None:
    print(json.dumps({"step": step, "result": result, "detail": detail}, ensure_ascii=False))


def read_env(path: str = ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 10.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""


def http_post(url: str, body: bytes, headers: dict[str, str] | None = None, timeout: float = 10.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""


def check_trello(env: dict[str, str]) -> tuple[str, str]:
    key = env.get("TRELLO_API_KEY") or os.environ.get("TRELLO_API_KEY", "")
    token = env.get("TRELLO_TOKEN") or os.environ.get("TRELLO_TOKEN", "")
    if not key or not token:
        return ("SKIPPED", "TRELLO_API_KEY or TRELLO_TOKEN missing")
    qs = urllib.parse.urlencode({"key": key, "token": token})
    url = f"https://api.trello.com/1/members/me/boards?{qs}"
    status, body = http_get(url, timeout=10.0)
    if status != 200:
        return ("FAIL", f"status={status} body={body[:200]!r}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return ("FAIL", f"json: {e}")
    if not isinstance(data, list):
        return ("FAIL", "expected JSON array of boards")
    return ("PASS", f"boards={len(data)}")


def check_opencode(env: dict[str, str]) -> tuple[str, str]:
    base = env.get("KANBAN_OPENCODE_URL") or os.environ.get("KANBAN_OPENCODE_URL", "")
    if not base:
        return ("SKIPPED", "KANBAN_OPENCODE_URL not set")
    user = env.get("OPENCODE_SERVER_USERNAME") or os.environ.get("OPENCODE_SERVER_USERNAME", "")
    pw = env.get("OPENCODE_SERVER_PASSWORD") or os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    if not user or not pw:
        return ("SKIPPED", "OPENCODE_SERVER_USERNAME or PASSWORD missing")

    import base64

    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    url = base.rstrip("/") + "/global/health"
    deadline = time.time() + 30.0
    last_status, last_body = 0, b""
    while time.time() < deadline:
        last_status, last_body = http_get(url, headers=headers, timeout=5.0)
        if last_status == 200:
            return ("PASS", f"status=200 body={last_body[:200]!r}")
        time.sleep(1.0)
    return ("FAIL", f"status={last_status} body={last_body[:200]!r}")


def main() -> int:
    env = read_env()
    results: dict[str, str] = {}

    for step, fn in (("trello", check_trello), ("opencode", check_opencode)):
        result, detail = fn(env)
        emit(step, result, detail)
        results[step] = result

    summary = " ".join(f"{k}={v}" for k, v in results.items())
    emit("SUMMARY", "", summary)

    has_fail = any(v == "FAIL" for v in results.values())
    return 2 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
