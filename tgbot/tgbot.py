#!/usr/bin/env python3
"""Simple Telegram Bot helper: fetch updates & send messages."""

import argparse
import configparser
import json
import logging
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

log = logging.getLogger("tgbot")

CONFIG_PATH = Path.home() / ".config" / "telegram" / "config.ini"
BASE_URL = "https://api.telegram.org/bot{token}"


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


def api_call(token: str, method: str, params: dict | None = None):
    url = f"{BASE_URL.format(token=token)}/{method}"
    log.debug("API call: %s params=%s", method, params)
    if params:
        data = json.dumps(params).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = Request(url)
    try:
        with urlopen(req) as resp:
            result = json.loads(resp.read())
            log.debug("API response: %s", result)
            return result
    except URLError as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        log.error("API %s failed: %s %s", method, e, body)
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
            from datetime import datetime, timezone
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
