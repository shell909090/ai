#!/usr/bin/env python3
"""Simple Telegram Bot helper: fetch updates, send messages, and run ACP sessions."""

import argparse
from collections import deque
import configparser
import json
import logging
import os
import queue
import re
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
MAX_PENDING_PROMPTS = 5
TG_COMMAND_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
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


class SessionLog:
    """Append structured session events to a per-session JSONL file."""

    def __init__(self, base_dir: Path, session_id: str):
        safe_session_id = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
        self.path = base_dir / f"session-{safe_session_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        os.close(fd)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def append(self, event: str, **fields):
        record = {
            "time": datetime.now().astimezone().isoformat(),
            "event": event,
            **fields,
        }
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")


def _state_dir() -> Path:
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state).expanduser() / "tgbot"
    return Path.home() / ".local" / "state" / "tgbot"


def _normalize_tg_command_name(name: str) -> str | None:
    command = name.strip().lstrip("/").lower().replace("-", "_")
    if not command or not TG_COMMAND_RE.fullmatch(command):
        return None
    return command


def _build_tg_commands(available_commands: list[dict]) -> list[dict]:
    commands: list[dict] = []
    seen: set[str] = set()
    for item in available_commands:
        raw_name = item.get("name", "")
        command = _normalize_tg_command_name(raw_name)
        if not command:
            log.warning("Skipping ACP slash command %r: incompatible with Telegram", raw_name)
            continue
        if command in seen:
            continue

        description = (
            item.get("description")
            or item.get("input", {}).get("hint")
            or f"Run /{command}"
        )
        description = " ".join(description.split())[:256] or f"Run /{command}"
        commands.append({"command": command, "description": description})
        seen.add(command)
        if len(commands) >= 100:
            break
    return commands


def _prompt_record(*, text: str, reply_chat_id: int, source: str,
                   from_id: int | None = None, username: str | None = None,
                   chat_type: str | None = None, message_id: int | None = None,
                   extra: dict | None = None) -> dict:
    """Build a normalized prompt record for processing and logging."""
    record = {
        "text": text,
        "reply_chat_id": reply_chat_id,
        "source": source,
        "from_id": from_id,
        "username": username or "",
        "chat_type": chat_type,
        "message_id": message_id,
    }
    if extra:
        record.update(extra)
    return record


def _prompt_log_fields(prompt: dict) -> dict:
    """Convert a prompt record to the common log field set."""
    return {
        "text": prompt.get("text"),
        "chat_id": prompt.get("reply_chat_id"),
        "source": prompt.get("source"),
        "from_id": prompt.get("from_id"),
        "username": prompt.get("username"),
        "chat_type": prompt.get("chat_type"),
        "message_id": prompt.get("message_id"),
    }


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

    def __init__(self, on_available_commands=None):
        self._proc: subprocess.Popen | None = None
        self.session_id: str | None = None
        self._req_id = 0
        self.available_commands: list[dict] = []
        self._on_available_commands = on_available_commands

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

    def _handle_session_update(self, update: dict):
        kind = update.get("sessionUpdate")
        if kind in ("available_commands_update", "availableCommandsUpdate"):
            commands = update.get("availableCommands")
            if commands is None:
                commands = update.get("available_commands", [])
            self.available_commands = commands or []
            if self._on_available_commands:
                self._on_available_commands(self.available_commands)
        return kind

    def _await_response(self, req_id: int) -> dict:
        """Wait for a specific ACP response while still consuming session updates."""
        while True:
            msg = self._recv()
            if msg.get("method") == "session/update" and "id" not in msg:
                self._handle_session_update(msg.get("params", {}).get("update", {}))
                continue
            if msg.get("id") == req_id:
                return msg

    # ── lifecycle ──────────────────────────────────────────────────────────

    @classmethod
    def start(cls, command: str, cwd: str, session_id: str | None = None,
              on_available_commands=None) -> "AcpSession":
        inst = cls(on_available_commands=on_available_commands)
        inst._proc = subprocess.Popen(
            shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=cwd,
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
            resp = inst._await_response(sess_req)
            if "error" in resp:
                inst._proc.kill()
                raise RuntimeError(f"ACP session/load failed: {resp}")
            inst.session_id = session_id
            log.info("ACP session loaded: %s", session_id)
        else:
            sess_req = inst._request("session/new", {"cwd": cwd, "mcpServers": []})
            resp = inst._await_response(sess_req)
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
                    kind = self._handle_session_update(upd)
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
                       yolo: bool, offset: int, buffer_prompt=None) -> tuple[str | None, int]:
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

    while True:
        resp = api_call(token, "getUpdates", {"timeout": 0, "offset": offset}, retries=3)
        for u in resp.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message", {})
            if msg.get("chat", {}).get("id") == chat_id:
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
                    api_call(token, "sendMessage", {
                        "chat_id": chat_id,
                        "text": "⚠️ 请回复 y/n 或选项编号",
                    }, retries=3)
                    continue

            if buffer_prompt is not None:
                buffer_prompt(u)

        if not resp.get("result"):
            time.sleep(0.5)


# ─── Group message helpers ───────────────────────────────────────────────────

def _bot_mention_ranges(text: str, entities: list, bot_username: str) -> list[tuple[int, int]]:
    """Return UTF-16 byte ranges for @bot_username mentions in a Telegram message."""
    bot_at = f"@{bot_username}".lower()
    utf16 = text.encode("utf-16-le")
    ranges: list[tuple[int, int]] = []
    for ent in entities:
        if ent.get("type") != "mention":
            continue
        start = ent["offset"] * 2
        end = (ent["offset"] + ent["length"]) * 2
        if utf16[start:end].decode("utf-16-le").lower() == bot_at:
            ranges.append((start, end))
    return ranges


def _strip_bot_mentions(text: str, entities: list, bot_username: str) -> str:
    """Remove all @bot_username mentions from text using Telegram's UTF-16 entity offsets."""
    remove = _bot_mention_ranges(text, entities, bot_username)
    if not remove:
        return text
    utf16 = text.encode("utf-16-le")
    parts = []
    prev = 0
    for start, end in sorted(remove):
        parts.append(utf16[prev:start])
        prev = end
    parts.append(utf16[prev:])
    return " ".join(b"".join(parts).decode("utf-16-le").split())


def _addressed_in_group(msg: dict, bot_id: int, bot_username: str) -> bool:
    """Return True if the group message is addressed to the bot (@mention or reply)."""
    # Reply to a message sent by the bot
    reply_from = msg.get("reply_to_message", {}).get("from", {})
    if reply_from.get("id") == bot_id:
        return True
    # Explicit @mention in entities
    text = msg.get("text", "")
    return bool(_bot_mention_ranges(text, msg.get("entities", []), bot_username))


def _extract_prompt(update: dict, allow_users: set[int], bot_id: int, bot_username: str) -> dict | None:
    """Return a normalized prompt payload for allowed Telegram messages."""
    msg = update.get("message", {})
    from_info = msg.get("from", {})
    from_id = from_info.get("id")
    reply_chat_id = msg.get("chat", {}).get("id")

    if from_id is None or reply_chat_id is None or from_id not in allow_users:
        return None

    chat_type = msg.get("chat", {}).get("type", "private")
    if chat_type in ("group", "supergroup") and not _addressed_in_group(msg, bot_id, bot_username):
        return None

    text = msg.get("text", "").strip()
    if not text:
        return None

    entities = msg.get("entities", [])
    if chat_type in ("group", "supergroup"):
        text = _strip_bot_mentions(text, entities, bot_username)
    if not text:
        return None

    return _prompt_record(
        text=text,
        reply_chat_id=reply_chat_id,
        source="telegram",
        from_id=from_id,
        username=from_info.get("username", ""),
        chat_type=chat_type,
        message_id=msg.get("message_id"),
    )


def _resolve_cwd(args, cfg: configparser.ConfigParser) -> tuple[Path, str]:
    """Resolve and validate the configured ACP working directory."""
    cwd_path = Path(args.cwd or cfg.get("acp", "cwd", fallback=str(Path.home()))).expanduser()
    if not cwd_path.exists():
        sys.exit(f"Error: cwd does not exist: {cwd_path}")
    if not cwd_path.is_dir():
        sys.exit(f"Error: cwd is not a directory: {cwd_path}")
    cwd_path = cwd_path.resolve()
    return cwd_path, str(cwd_path)


def _load_allow_users(cfg: configparser.ConfigParser, owner_chat_id: int) -> set[int]:
    """Load the allow_users whitelist from config."""
    allow_str = cfg.get("bot", "allow_users", fallback="")
    return (
        {int(x.strip()) for x in allow_str.split(",") if x.strip()}
        if allow_str else {owner_chat_id}
    )


def _load_cron_jobs(cfg: configparser.ConfigParser) -> list[dict]:
    """Load cron jobs from the configured markdown file."""
    cron_file_str = cfg.get("cron", "file", fallback=None)
    if not cron_file_str:
        return []
    cron_path = Path(cron_file_str).expanduser()
    if not cron_path.exists():
        log.warning("Cron file not found: %s", cron_path)
        return []
    jobs = parse_crontab(cron_path)
    log.info("Loaded %d cron job(s) from %s", len(jobs), cron_path)
    return jobs


class TelegramReply:
    """Manage the lifecycle of a streamed Telegram reply message."""

    def __init__(self, token: str, chat_id: int, max_text: int):
        self._token = token
        self.chat_id = chat_id
        self._max_text = max_text
        result = api_call(token, "sendMessage", {"chat_id": chat_id, "text": "⏳"}, retries=3)
        if not result.get("ok"):
            raise RuntimeError(f"sendMessage failed: {result}")
        self.message_id = result["result"]["message_id"]
        self.offset = 0

    def update(self, text: str):
        """Stream partial text into Telegram, splitting if the message grows too large."""
        segment = text[self.offset:]
        display = (segment + "▌") if segment else "⏳"
        if len(display) > self._max_text:
            cut = segment.rfind("\n", 0, self._max_text)
            if cut < 0:
                cut = self._max_text - 1
            try:
                api_call(self._token, "editMessageText", {
                    "chat_id": self.chat_id,
                    "message_id": self.message_id,
                    "text": segment[:cut],
                }, retries=3)
            except SystemExit:
                pass
            self.offset += cut
            result = api_call(
                self._token,
                "sendMessage",
                {"chat_id": self.chat_id, "text": "⏳"},
                retries=3,
            )
            if result.get("ok"):
                self.message_id = result["result"]["message_id"]
            return

        try:
            result = api_call(self._token, "editMessageText", {
                "chat_id": self.chat_id,
                "message_id": self.message_id,
                "text": display,
            }, retries=3)
            if not result.get("ok"):
                desc = result.get("description", "")
                if "not modified" not in desc:
                    log.warning("editMessageText: %s", desc or result)
        except SystemExit:
            log.warning("editMessageText failed after retries, skipping")

    def fail(self, text: str):
        """Finalize the current Telegram message with an error."""
        api_call(self._token, "editMessageText", {
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "text": text,
        }, retries=3)

    def finalize(self, text: str):
        """Finalize the current Telegram message with the remaining response text."""
        tail = text[self.offset:] if text else ""
        api_call(self._token, "editMessageText", {
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "text": tail or "(无回复)",
        }, retries=3)


# ─── ACP daemon ───────────────────────────────────────────────────────────────

def _sync_telegram_commands(token: str, available_commands: list[dict],
                            commands_state: dict, session_log: SessionLog | None):
    """Sync ACP-exposed slash commands to Telegram."""
    tg_commands = _build_tg_commands(available_commands)
    signature = json.dumps(tg_commands, ensure_ascii=False, sort_keys=True)

    if tg_commands:
        if signature == commands_state["signature"]:
            return
        result = api_call(token, "setMyCommands", {"commands": tg_commands}, retries=3)
        if not result.get("ok"):
            log.warning("setMyCommands failed: %s", result)
            return
        commands_state["signature"] = signature
        commands_state["registered"] = True
        commands_state["current"] = tg_commands
        log.info("Registered %d ACP slash command(s) with Telegram", len(tg_commands))
        if session_log is not None:
            session_log.append("commands_registered", count=len(tg_commands), commands=tg_commands)
        return

    if commands_state["registered"]:
        result = api_call(token, "deleteMyCommands", {}, retries=3)
        if not result.get("ok"):
            log.warning("deleteMyCommands failed: %s", result)
            return
        commands_state["signature"] = signature
        commands_state["registered"] = False
        commands_state["current"] = []
        log.info("Cleared ACP slash commands from Telegram")
        if session_log is not None:
            session_log.append("commands_cleared")


def _enqueue_prompt(token: str, pending_prompts: deque[dict], session_log: SessionLog | None,
                    prompt: dict) -> bool:
    """Buffer a prompt during permission handling."""
    if len(pending_prompts) >= MAX_PENDING_PROMPTS:
        log.warning(
            "Dropping buffered prompt from [%d @%s] chat=%d: queue full (%d)",
            prompt.get("from_id"),
            prompt.get("username", ""),
            prompt.get("reply_chat_id"),
            len(pending_prompts),
        )
        if session_log is not None:
            session_log.append(
                "prompt_dropped",
                reason="buffer_full",
                queue_size=len(pending_prompts),
                **_prompt_log_fields(prompt),
            )
        try:
            api_call(token, "sendMessage", {
                "chat_id": prompt["reply_chat_id"],
                "text": "⚠️ 当前正在等待权限确认，排队已满，请稍后重试。",
            }, retries=3)
        except SystemExit:
            log.warning("sendMessage failed after retries, drop notice skipped")
        return False

    pending_prompts.append(prompt)
    log.info(
        "Buffered prompt from [%d @%s] chat=%d pending=%d",
        prompt.get("from_id"),
        prompt.get("username", ""),
        prompt.get("reply_chat_id"),
        len(pending_prompts),
    )
    if session_log is not None:
        session_log.append(
            "prompt_buffered",
            queue_size=len(pending_prompts),
            **_prompt_log_fields(prompt),
        )
    return True


def _handle_prompt(token: str, acp: AcpSession, session_log: SessionLog | None, prompt: dict,
                   max_tg: int, turn_id: int, on_permission) -> int:
    """Run one prompt through ACP and stream the reply back to Telegram."""
    turn_id += 1
    current_turn_id = turn_id

    if session_log is not None:
        payload = {
            "turn_id": current_turn_id,
            "session_id": acp.session_id,
            **_prompt_log_fields(prompt),
        }
        extra_keys = set(prompt.keys()) - {
            "text", "reply_chat_id", "source", "from_id", "username", "chat_type", "message_id",
        }
        for key in extra_keys:
            payload[key] = prompt[key]
        session_log.append("incoming_prompt", **payload)

    try:
        reply = TelegramReply(token, prompt["reply_chat_id"], max_tg)
    except RuntimeError as e:
        log.error("%s", e)
        return turn_id

    try:
        response = acp.prompt(prompt["text"], on_chunk=reply.update, on_permission=on_permission)
    except Exception as e:
        log.error("ACP prompt failed: %s", e)
        error_text = f"❌ {e}"
        reply.fail(error_text)
        if session_log is not None:
            session_log.append(
                "outgoing_response",
                turn_id=current_turn_id,
                session_id=acp.session_id,
                source=prompt["source"],
                chat_id=prompt["reply_chat_id"],
                message_id=reply.message_id,
                status="error",
                text=error_text,
            )
        return turn_id

    final_text = response or "(无回复)"
    reply.finalize(final_text)
    if session_log is not None:
        session_log.append(
            "outgoing_response",
            turn_id=current_turn_id,
            session_id=acp.session_id,
            source=prompt["source"],
            chat_id=prompt["reply_chat_id"],
            message_id=reply.message_id,
            status="ok",
            text=final_text,
        )
    return turn_id


def _drain_pending_prompt(token: str, acp: AcpSession, session_log: SessionLog | None,
                          pending_prompts: deque[dict], max_tg: int, turn_id: int,
                          on_permission) -> tuple[bool, int]:
    """Drain one buffered prompt if available."""
    if not pending_prompts:
        return False, turn_id

    prompt = pending_prompts.popleft()
    log.info(
        "Draining buffered prompt from [%d @%s] chat=%d pending=%d",
        prompt.get("from_id"),
        prompt.get("username", ""),
        prompt.get("reply_chat_id"),
        len(pending_prompts),
    )
    if session_log is not None:
        session_log.append(
            "prompt_dequeued",
            queue_size=len(pending_prompts),
            **_prompt_log_fields(prompt),
        )
    return True, _handle_prompt(token, acp, session_log, prompt, max_tg, turn_id, on_permission)


def _process_telegram_updates(token: str, allow_users: set[int], bot_id: int, bot_username: str,
                              offset: int, acp: AcpSession, session_log: SessionLog | None,
                              max_tg: int, turn_id: int, on_permission) -> int:
    """Fetch and process one batch of Telegram updates."""
    resp = api_call(token, "getUpdates", {"timeout": 30, "offset": offset}, retries=3)
    if not resp.get("ok"):
        log.warning("getUpdates failed: %s", resp)
        time.sleep(2)
        return offset, turn_id

    for update in resp.get("result", []):
        if update["update_id"] + 1 <= offset:
            continue
        offset = update["update_id"] + 1

        prompt = _extract_prompt(update, allow_users, bot_id, bot_username)
        if prompt is None:
            continue

        log.info(
            "ACP prompt from [%d @%s] chat=%d",
            prompt.get("from_id"),
            prompt.get("username", ""),
            prompt.get("reply_chat_id"),
        )
        turn_id = _handle_prompt(token, acp, session_log, prompt, max_tg, turn_id, on_permission)

    return offset, turn_id


def _run_due_cron_jobs(cron_jobs: list[dict], cron_last: dict[int, tuple], owner_chat_id: int,
                       token: str, acp: AcpSession, session_log: SessionLog | None,
                       max_tg: int, turn_id: int, on_permission) -> int:
    """Run cron prompts that are due in the current minute."""
    now = datetime.now()
    now_key = (now.year, now.month, now.day, now.hour, now.minute)
    for i, job in enumerate(cron_jobs):
        if _cron_matches(job["expr"], now) and cron_last.get(i) != now_key:
            cron_last[i] = now_key
            log.info("Cron[%d] firing: %s", i, job["expr"])
            prompt = _prompt_record(
                text=job["prompt"],
                reply_chat_id=owner_chat_id,
                source="cron",
                chat_type="private",
                extra={"cron_expr": job["expr"], "cron_index": i},
            )
            turn_id = _handle_prompt(token, acp, session_log, prompt, max_tg, turn_id, on_permission)
    return turn_id


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

    cwd_path, cwd = _resolve_cwd(args, cfg)
    allow_users = _load_allow_users(cfg, owner_chat_id)
    cron_jobs = _load_cron_jobs(cfg)
    cron_last: dict[int, tuple] = {}

    me = api_call(token, "getMe")
    if not me.get("ok"):
        sys.exit(f"Error: getMe failed: {me}")
    bot_id: int = me["result"]["id"]
    bot_username: str = me["result"]["username"]
    log.info("ACP bot: @%s (id=%d)", bot_username, bot_id)

    session_log: SessionLog | None = None
    pending_prompts: deque[dict] = deque()
    commands_state = {
        "signature": None,
        "registered": False,
        "current": [],
    }

    def sync_telegram_commands(available_commands: list[dict]):
        _sync_telegram_commands(token, available_commands, commands_state, session_log)

    log.info("Starting ACP: cmd=%r cwd=%r yolo=%s session=%s",
             acp_cmd, cwd, args.yolo, args.session_id)
    acp = AcpSession.start(
        acp_cmd,
        cwd,
        session_id=args.session_id,
        on_available_commands=sync_telegram_commands,
    )
    session_log = SessionLog(_state_dir(), acp.session_id)
    session_log.append(
        "session_started",
        session_id=acp.session_id,
        cwd=cwd,
        agent_command=acp_cmd,
        resumed=bool(args.session_id),
        log_path=str(session_log.path),
    )
    if commands_state["current"]:
        session_log.append(
            "commands_registered",
            count=len(commands_state["current"]),
            commands=commands_state["current"],
        )
    print(f"ACP session ready: {acp.session_id}", flush=True)

    offset = 0
    max_tg = 4000
    turn_id = 0

    def buffer_allowed_prompt(update: dict):
        prompt = _extract_prompt(update, allow_users, bot_id, bot_username)
        if prompt is None:
            return False
        return _enqueue_prompt(token, pending_prompts, session_log, prompt)

    def on_permission(params):
        nonlocal offset
        option_id, offset = _handle_permission(
            token, owner_chat_id, params, args.yolo, offset, buffer_prompt=buffer_allowed_prompt
        )
        return option_id

    try:
        while True:
            drained, turn_id = _drain_pending_prompt(
                token, acp, session_log, pending_prompts, max_tg, turn_id, on_permission
            )
            if drained:
                continue

            offset, turn_id = _process_telegram_updates(
                token, allow_users, bot_id, bot_username, offset,
                acp, session_log, max_tg, turn_id, on_permission,
            )
            turn_id = _run_due_cron_jobs(
                cron_jobs, cron_last, owner_chat_id, token, acp, session_log,
                max_tg, turn_id, on_permission,
            )
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
                       help="Working directory for agent process and ACP session")
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
