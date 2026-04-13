#!/usr/bin/env python3
"""Simple Telegram Bot helper: fetch updates, send messages, and run ACP sessions."""

import argparse
import configparser
import json
import logging
import queue
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from http.client import RemoteDisconnected
from urllib.error import URLError, HTTPError

log = logging.getLogger("tgbot")

CONFIG_PATH = Path.home() / ".config" / "telegram" / "config.ini"
BASE_URL = "https://api.telegram.org/bot{token}"
_retry_delay = 3  # seconds between network-error retries


def load_config(path: Path = CONFIG_PATH) -> configparser.ConfigParser:
    if not path.exists():
        sys.exit(
            f"Error: config not found at {path}\n"
            f"Create it with:\n\n"
            f"  [bot]\n"
            f"  token = YOUR_BOT_TOKEN\n"
            f"  chat_id = YOUR_CHAT_ID\n"
        )
    cfg = configparser.ConfigParser()
    cfg.read(path)
    if "bot" not in cfg:
        sys.exit(f"Error: [bot] section missing in {path}")
    if not cfg["bot"].get("token"):
        sys.exit(f"Error: token not set in {path}")
    log.debug("Config loaded from %s", path)
    return cfg


def api_call(token: str, method: str, params: dict | None = None, retries: int = 0):
    url = f"{BASE_URL.format(token=token)}/{method}"
    data = json.dumps(params).encode() if params else None
    for attempt in range(retries + 1):
        log.debug("API call: %s params=%s", method, params)
        req = Request(url, data=data, headers={"Content-Type": "application/json"}) if data \
            else Request(url)
        try:
            with urlopen(req) as resp:
                result = json.loads(resp.read())
                log.debug("API response: %s", result)
                return result
        except HTTPError as e:
            # HTTP 4xx/5xx — parse body and return; caller checks result["ok"]
            body = e.read().decode()
            log.error("API %s HTTP %d: %s", method, e.code, body)
            try:
                return json.loads(body)
            except Exception:
                return {"ok": False, "description": body}
        except (URLError, RemoteDisconnected) as e:
            # Network error — retry up to `retries` times
            log.error("API %s failed: %s", method, e)
            if attempt < retries:
                log.warning("Retrying %s in %ds… (%d/%d)", method, _retry_delay, attempt + 1, retries)
                time.sleep(_retry_delay)
                continue
            sys.exit(1)


def cmd_get(args):
    """Fetch new messages via getUpdates."""
    cfg = load_config()
    token = cfg["bot"]["token"]
    my_chat_id = cfg["bot"].get("chat_id")
    if my_chat_id:
        my_chat_id = int(my_chat_id)
    result = api_call(token, "getUpdates", {"timeout": 0})
    if not result.get("ok"):
        log.error("getUpdates failed: %s", result)
        sys.exit(1)
    updates = result.get("result", [])
    if not updates:
        print("No new messages." if not args.json else "[]")
        return
    json_out = []
    has_output = False
    for u in updates:
        msg = u.get("message", {})
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        sender = msg.get("from", {})
        text = msg.get("text", "")
        date = msg.get("date", 0)
        is_mine = my_chat_id and chat_id == my_chat_id
        if not args.all and not is_mine:
            log.debug("Hiding message from chat_id=%s", chat_id)
            continue
        has_output = True
        if args.json:
            from datetime import timezone
            json_out.append({
                "time": datetime.fromtimestamp(date, tz=timezone.utc).isoformat(),
                "chat_id": chat_id,
                "is_default_chat": is_mine,
                "from": sender.get("first_name", "?"),
                "text": text,
            })
        elif is_mine:
            print(f"{sender.get('first_name', '?')}: {text}")
        else:
            print(f"[chat_id={chat_id}] {sender.get('first_name', '?')}: {text}")
    if args.json:
        print(json.dumps(json_out, ensure_ascii=False, indent=2))
    elif not has_output:
        print("No new messages.")
    # always confirm all updates
    last_id = updates[-1]["update_id"]
    api_call(token, "getUpdates", {"offset": last_id + 1, "timeout": 0})


def cmd_send(args):
    """Send a message to the specified chat."""
    cfg = load_config()
    token = cfg["bot"]["token"]
    chat_id = args.chat_id or cfg["bot"].get("chat_id")
    if not chat_id:
        log.error("chat_id not provided and not set in config")
        sys.exit(1)
    try:
        chat_id = int(chat_id)
    except ValueError:
        log.error("Invalid chat_id: %s", chat_id)
        sys.exit(1)
    log.info("Sending to chat_id=%d", chat_id)
    result = api_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": args.text,
    })
    if not result.get("ok"):
        log.error("sendMessage failed: %s", result)
        sys.exit(1)
    print(f"Message sent to {chat_id}.")


# ─── ACP session ──────────────────────────────────────────────────────────────

class AcpSession:
    """Manages an ACP-compatible agent subprocess (Claude Code, Codex, OpenCode, …)."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self.session_id: str | None = None
        self._req_id = 0

    # ── low-level I/O ─────────────────────────────────────────────────────

    def _send(self, msg: dict):
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()
        log.debug("ACP → %s", line.rstrip())

    def _recv(self) -> dict:
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("ACP agent process closed stdout unexpectedly")
        log.debug("ACP ← %s", line.rstrip())
        return json.loads(line)

    def _request(self, method: str, params: dict) -> int:
        rid = self._req_id
        self._req_id += 1
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return rid

    def _reply(self, req_id: int, result):
        self._send({"jsonrpc": "2.0", "id": req_id, "result": result})

    # ── lifecycle ──────────────────────────────────────────────────────────

    @classmethod
    def start(cls, command: str, cwd: str, session_id: str | None = None) -> "AcpSession":
        inst = cls()
        inst._proc = subprocess.Popen(
            shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # 1. initialize
        init_id = inst._request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
            "clientInfo": {"name": "tgbot", "title": "Telegram Bot ACP Client", "version": "1.0"},
        })
        resp = inst._recv()
        if resp.get("id") != init_id or "error" in resp:
            inst._proc.kill()
            raise RuntimeError(f"ACP initialize failed: {resp}")
        log.info("ACP initialized: agent=%s",
                 resp["result"].get("agentInfo", {}).get("name", "?"))

        # 2. session: load existing or create new
        if session_id:
            sess_req = inst._request("session/load", {"sessionId": session_id, "cwd": cwd, "mcpServers": []})
            while True:
                msg = inst._recv()
                if "id" in msg and msg["id"] == sess_req:
                    break
            inst.session_id = session_id
            log.info("ACP session loaded: %s", session_id)
        else:
            sess_req = inst._request("session/new", {"cwd": cwd, "mcpServers": []})
            resp = inst._recv()
            if resp.get("id") != sess_req or "error" in resp:
                inst._proc.kill()
                raise RuntimeError(f"ACP session/new failed: {resp}")
            inst.session_id = resp["result"]["sessionId"]
            log.info("ACP new session: %s", inst.session_id)

        return inst

    def close(self):
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()

    # ── prompt turn ────────────────────────────────────────────────────────

    def prompt(self, text: str, on_chunk, on_permission) -> str:
        """
        Send a user message and return the complete response text.

        on_chunk(accumulated: str)
            Called on each newline; use for line-buffered streaming edits.
        on_permission(params: dict) -> str | None
            Called when agent requests permission; return optionId or None to cancel.

        A background thread reads the agent's stdout so that Telegram API calls
        in on_chunk never block the agent's output pipe.
        """
        req_id = self._request("session/prompt", {
            "sessionId": self.session_id,
            "prompt": [{"type": "text", "text": text}],
        })

        msg_q: queue.Queue = queue.Queue()

        def _reader():
            try:
                while True:
                    msg = self._recv()
                    msg_q.put(msg)
                    if "id" in msg and "method" not in msg and msg.get("id") == req_id:
                        break
            except Exception as e:
                msg_q.put(e)

        threading.Thread(target=_reader, daemon=True).start()

        parts: list[str] = []

        while True:
            msg = msg_q.get()

            if isinstance(msg, Exception):
                raise msg

            has_id = "id" in msg
            has_method = "method" in msg

            # Agent → Client request (agent is blocked until we reply)
            if has_method and has_id:
                if msg["method"] == "session/request_permission":
                    option_id = on_permission(msg["params"])
                    if option_id is None:
                        self._reply(msg["id"], {"outcome": {"outcome": "cancelled"}})
                    else:
                        self._reply(msg["id"], {
                            "outcome": {"outcome": "selected", "optionId": option_id}
                        })
                else:
                    self._reply(msg["id"], {
                        "error": {"code": -32601, "message": "Not supported"}
                    })
                continue

            # Notification from agent (no reply expected)
            if has_method and not has_id:
                if msg["method"] == "session/update":
                    upd = msg["params"].get("update", {})
                    kind = upd.get("sessionUpdate")
                    if kind == "agent_message_chunk":
                        chunk = upd.get("content", {}).get("text", "")
                        parts.append(chunk)
                        if "\n" in chunk:
                            on_chunk("".join(parts))
                    elif kind == "tool_call":
                        log.debug("tool_call update: %s", upd)
                        title = upd.get("title", "tool")
                        tool_kind = upd.get("kind", "")
                        locations = upd.get("locations", [])
                        line = f"\n🔧 [{tool_kind}] {title}" if tool_kind else f"\n🔧 {title}"
                        if locations:
                            paths = ", ".join(
                                l.get("path", str(l)) for l in locations[:3]
                            )
                            line += f" ({paths})"
                        parts.append(line + "\n")
                        on_chunk("".join(parts))
                continue

            # Final response to our session/prompt — done
            if has_id and not has_method and msg.get("id") == req_id:
                return "".join(parts)


# ─── Cron helpers ─────────────────────────────────────────────────────────────

def parse_crontab(path: Path) -> list[dict]:
    """Parse crontab.md: ## <cron-expr> headers, body paragraph is the prompt text."""
    jobs: list[dict] = []
    current_expr: str | None = None
    current_lines: list[str] = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("## "):
                if current_expr is not None:
                    prompt = "\n".join(current_lines).strip()
                    if prompt:
                        jobs.append({"expr": current_expr, "prompt": prompt})
                current_expr = line[3:].strip()
                current_lines = []
            elif current_expr is not None:
                current_lines.append(line)
    if current_expr is not None:
        prompt = "\n".join(current_lines).strip()
        if prompt:
            jobs.append({"expr": current_expr, "prompt": prompt})
    return jobs


def _cron_field_matches(field: str, value: int, lo: int, hi: int) -> bool:
    for part in field.split(","):
        if part == "*":
            return True
        if "/" in part:
            r, step = part.split("/", 1)
            step = int(step)
            if r == "*":
                start, end = lo, hi
            elif "-" in r:
                start, end = map(int, r.split("-"))
            else:
                start, end = int(r), hi
            if start <= value <= end and (value - start) % step == 0:
                return True
        elif "-" in part:
            a, b = map(int, part.split("-"))
            if a <= value <= b:
                return True
        else:
            if int(part) == value:
                return True
    return False


def _cron_matches(expr: str, dt: datetime) -> bool:
    """True if the 5-field cron expression matches dt (dow: 0=Sun … 6=Sat, standard cron)."""
    parts = expr.split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    dt_dow = dt.isoweekday() % 7  # isoweekday: Mon=1..Sun=7 → 0=Sun, 1=Mon, …, 6=Sat
    return (
        _cron_field_matches(minute, dt.minute, 0, 59) and
        _cron_field_matches(hour, dt.hour, 0, 23) and
        _cron_field_matches(dom, dt.day, 1, 31) and
        _cron_field_matches(month, dt.month, 1, 12) and
        _cron_field_matches(dow, dt_dow, 0, 6)
    )


# ─── Permission handling ──────────────────────────────────────────────────────

def _handle_permission(token: str, chat_id: int, params: dict,
                       yolo: bool, offset: int) -> tuple[str | None, int]:
    """
    Handle a session/request_permission from the agent.
    Returns (option_id_or_None, updated_offset).

    In yolo mode: auto-selects the first allow option.
    Otherwise: sends a Telegram message to chat_id and short-polls for a valid reply.
    Valid replies: y/Y/n/N or a bare integer option number.
    """
    options = params.get("options", [])

    if yolo:
        for opt in options:
            if "allow" in opt.get("kind", "").lower():
                return opt["optionId"], offset
        return (options[0]["optionId"] if options else "allow-once"), offset

    tool_call = params.get("toolCall", {})
    lines = ["⚠️ 权限请求"]
    if tool_call.get("toolCallId"):
        lines.append(f"工具: {tool_call['toolCallId']}")
    for i, opt in enumerate(options, 1):
        lines.append(f"{i}) {opt['name']}")
    lines.append("\n回复 y（允许）/ n（拒绝）或选项编号")
    api_call(token, "sendMessage", {"chat_id": chat_id, "text": "\n".join(lines)}, retries=3)

    hint_sent = False
    while True:
        resp = api_call(token, "getUpdates", {"timeout": 0, "offset": offset}, retries=3)
        for u in resp.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message", {})
            if msg.get("chat", {}).get("id") != chat_id:
                continue
            reply = msg.get("text", "").strip()
            lower = reply.lower()

            if lower in ("y", "n"):
                if lower == "n":
                    return None, offset
                for opt in options:
                    if "allow" in opt.get("kind", "").lower():
                        return opt["optionId"], offset
                return (options[0]["optionId"] if options else "allow-once"), offset

            if reply.isdigit():
                idx = int(reply) - 1
                if 0 <= idx < len(options):
                    return options[idx]["optionId"], offset
                # out-of-range falls through to hint

            if not hint_sent:
                api_call(token, "sendMessage", {
                    "chat_id": chat_id,
                    "text": "⚠️ 请回复 y/n 或选项编号",
                }, retries=3)
                hint_sent = True

        if not resp.get("result"):
            time.sleep(0.5)


# ─── ACP daemon ───────────────────────────────────────────────────────────────

def cmd_acp(args):
    cfg = load_config()
    token = cfg["bot"]["token"]
    my_chat_id = cfg["bot"].get("chat_id")
    if not my_chat_id:
        sys.exit("Error: chat_id not set in config")
    owner_chat_id = int(my_chat_id)

    acp_cmd = args.agent_cmd or cfg.get("acp", "command", fallback=None)
    if not acp_cmd:
        sys.exit(
            "Error: ACP command not configured. "
            "Set [acp] command in config or use --agent-cmd"
        )
    cwd = args.cwd or cfg.get("acp", "cwd", fallback=str(Path.home()))

    # allow_users: comma-separated Telegram user IDs allowed to send commands.
    # If unset, only the owner (chat_id) may interact.
    allow_str = cfg.get("bot", "allow_users", fallback="")
    allow_users: set[int] = (
        {int(x.strip()) for x in allow_str.split(",") if x.strip()}
        if allow_str else {owner_chat_id}
    )

    # cron jobs from markdown file
    cron_jobs: list[dict] = []
    cron_file_str = cfg.get("cron", "file", fallback=None)
    if cron_file_str:
        cron_path = Path(cron_file_str).expanduser()
        if cron_path.exists():
            cron_jobs = parse_crontab(cron_path)
            log.info("Loaded %d cron job(s) from %s", len(cron_jobs), cron_path)
        else:
            log.warning("Cron file not found: %s", cron_path)
    cron_last: dict[int, tuple] = {}  # job index → (year, month, day, hour, minute)

    log.info("Starting ACP: cmd=%r cwd=%r yolo=%s session=%s",
             acp_cmd, cwd, args.yolo, args.session_id)
    acp = AcpSession.start(acp_cmd, cwd, session_id=args.session_id)
    print(f"ACP session ready: {acp.session_id}", flush=True)

    offset = 0
    MAX_TG = 4000

    def on_permission(params):
        nonlocal offset
        # Permission dialogs always go to owner, regardless of which chat triggered the prompt
        option_id, offset = _handle_permission(
            token, owner_chat_id, params, args.yolo, offset
        )
        return option_id

    def handle_prompt(text: str, reply_chat_id: int):
        """Send text to ACP and stream the response back to reply_chat_id."""
        sr = api_call(token, "sendMessage", {"chat_id": reply_chat_id, "text": "⏳"}, retries=3)
        if not sr.get("ok"):
            log.error("sendMessage failed: %s", sr)
            return

        edit_state = {"id": sr["result"]["message_id"], "offset": 0, "chat_id": reply_chat_id}

        def on_chunk(t, _es=edit_state):
            segment = t[_es["offset"]:]
            display = (segment + "▌") if segment else "⏳"
            if len(display) > MAX_TG:
                # Finalize current message at a line boundary, start a new one
                cut = segment.rfind("\n", 0, MAX_TG)
                if cut < 0:
                    cut = MAX_TG - 1
                try:
                    api_call(token, "editMessageText", {
                        "chat_id": _es["chat_id"],
                        "message_id": _es["id"],
                        "text": segment[:cut],
                    }, retries=3)
                except SystemExit:
                    pass
                _es["offset"] += cut
                sr2 = api_call(token, "sendMessage",
                               {"chat_id": _es["chat_id"], "text": "⏳"}, retries=3)
                if sr2.get("ok"):
                    _es["id"] = sr2["result"]["message_id"]
                return
            try:
                result = api_call(token, "editMessageText", {
                    "chat_id": _es["chat_id"],
                    "message_id": _es["id"],
                    "text": display,
                }, retries=3)
                if not result.get("ok"):
                    desc = result.get("description", "")
                    if "not modified" not in desc:
                        log.warning("editMessageText: %s", desc or result)
            except SystemExit:
                log.warning("editMessageText failed after retries, skipping")

        try:
            response = acp.prompt(text, on_chunk=on_chunk, on_permission=on_permission)
        except Exception as e:
            log.error("ACP prompt failed: %s", e)
            api_call(token, "editMessageText", {
                "chat_id": edit_state["chat_id"],
                "message_id": edit_state["id"],
                "text": f"❌ {e}",
            }, retries=3)
            return

        tail = response[edit_state["offset"]:] if response else ""
        api_call(token, "editMessageText", {
            "chat_id": edit_state["chat_id"],
            "message_id": edit_state["id"],
            "text": tail or "(无回复)",
        }, retries=3)

    try:
        while True:
            resp = api_call(token, "getUpdates", {"timeout": 30, "offset": offset}, retries=3)
            if not resp.get("ok"):
                log.warning("getUpdates failed: %s", resp)
                time.sleep(2)
                continue

            for u in resp.get("result", []):
                if u["update_id"] + 1 <= offset:
                    continue
                offset = u["update_id"] + 1

                msg = u.get("message", {})
                from_info = msg.get("from", {})
                from_id = from_info.get("id")
                username = from_info.get("username", "")
                reply_chat_id = msg.get("chat", {}).get("id")

                if from_id is None or reply_chat_id is None:
                    continue
                if from_id not in allow_users:
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    continue

                log.info("ACP ← [%d @%s] %s", from_id, username, text)
                handle_prompt(text, reply_chat_id)

            # fire any due cron jobs
            now = datetime.now()
            now_key = (now.year, now.month, now.day, now.hour, now.minute)
            for i, job in enumerate(cron_jobs):
                if _cron_matches(job["expr"], now) and cron_last.get(i) != now_key:
                    cron_last[i] = now_key
                    log.info("Cron[%d] firing: %s", i, job["expr"])
                    handle_prompt(job["prompt"], owner_chat_id)

    finally:
        acp.close()


def main():
    parser = argparse.ArgumentParser(description="Telegram Bot helper")
    parser.add_argument("-l", "--log-level", default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level (default: WARNING)")
    sub = parser.add_subparsers(dest="command")

    p_get = sub.add_parser("get", help="Fetch new messages (getUpdates)")
    p_get.add_argument("-a", "--all", action="store_true",
                       help="Show messages from all chats")
    p_get.add_argument("-j", "--json", action="store_true",
                       help="Output in JSON format")

    p_send = sub.add_parser("send", help="Send a message")
    p_send.add_argument("-c", "--chat-id", default=None,
                        help="Target chat ID (default: from config)")
    p_send.add_argument("text", help="Message text")

    p_acp = sub.add_parser("acp", help="Run ACP daemon (Telegram ↔ ACP agent)")
    p_acp.add_argument("--agent-cmd", default=None, metavar="CMD",
                       help="ACP agent command (overrides [acp] command in config)")
    p_acp.add_argument("--cwd", default=None,
                       help="Working directory for agent (overrides [acp] cwd in config)")
    p_acp.add_argument("--session-id", default=None, metavar="UUID",
                       help="Resume an existing ACP session")
    p_acp.add_argument("--yolo", action="store_true",
                       help="Auto-approve all permission requests without asking")

    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "get":
        cmd_get(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "acp":
        cmd_acp(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
