#!/usr/bin/env python3
"""kanbanctl.py — CLI for the kanban coordinator Control API.

Reads KANBAN_CONTROL_URL and KANBAN_CONTROL_TOKEN from environment.
The coordinator holds Trello credentials; this script never calls Trello directly.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def get_config() -> tuple[str, str]:
    """Return (base_url, token) from environment."""
    url = os.environ.get("KANBAN_CONTROL_URL", "")
    token = os.environ.get("KANBAN_CONTROL_TOKEN", "")
    if not url:
        die("KANBAN_CONTROL_URL is not set")
    if not token:
        die("KANBAN_CONTROL_TOKEN is not set")
    return url.rstrip("/"), token


def die(msg: str, code: int = 1) -> None:
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(code)


def request(method: str, path: str, body: dict | None = None) -> dict:
    """Make an authenticated request to the Control API."""
    base_url, token = get_config()
    url = f"{base_url}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            err = json.loads(body_bytes)
            die(f"HTTP {e.code}: {err.get('error', body_bytes.decode())}")
        except json.JSONDecodeError:
            die(f"HTTP {e.code}: {body_bytes.decode()}")
    except urllib.error.URLError as e:
        die(f"connection error: {e.reason}")


def cmd_list_cards(args: argparse.Namespace) -> None:
    cards = request("GET", f"/control/v1/cards?list={args.list}")
    print(json.dumps(cards, indent=2, ensure_ascii=False))


def cmd_show_card(args: argparse.Namespace) -> None:
    card = request("GET", f"/control/v1/cards/{args.card_id}")
    print(json.dumps(card, indent=2, ensure_ascii=False))


def cmd_add_todo(args: argparse.Namespace) -> None:
    body: dict = {"title": args.title, "description": args.desc or ""}
    if args.project:
        body["project"] = args.project
    else:
        body["cwd"] = os.getcwd()
    if args.model:
        body["model"] = args.model
    for label in args.label or []:
        body.setdefault("labels", []).append(label)
    card = request("POST", "/control/v1/cards", body)
    print(json.dumps(card, indent=2, ensure_ascii=False))


def cmd_move(args: argparse.Namespace) -> None:
    result = request("POST", f"/control/v1/cards/{args.card_id}/move", {"list": args.list})
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_comment(args: argparse.Namespace) -> None:
    result = request("POST", f"/control/v1/cards/{args.card_id}/comments", {"text": args.text})
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_label_add(args: argparse.Namespace) -> None:
    result = request("POST", f"/control/v1/cards/{args.card_id}/labels", {"label": args.label})
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_label_remove(args: argparse.Namespace) -> None:
    label_path = urllib.request.quote(args.label, safe="")
    result = request("DELETE", f"/control/v1/cards/{args.card_id}/labels/{label_path}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kanbanctl.py",
        description="Kanban coordinator Control API client",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list-cards
    p = sub.add_parser("list-cards", help="List cards in a list")
    p.add_argument("--list", default="todo", help="List name: todo, doing, done")
    p.set_defaults(func=cmd_list_cards)

    # show-card
    p = sub.add_parser("show-card", help="Show a card by ID")
    p.add_argument("card_id")
    p.set_defaults(func=cmd_show_card)

    # add-todo
    p = sub.add_parser("add-todo", help="Create a new todo card")
    p.add_argument("--title", required=True, help="Card title")
    p.add_argument("--desc", default="", help="Card description")
    p.add_argument("--project", help="Project name override (default: infer from cwd)")
    p.add_argument("--model", help="Model alias (e.g. sonnet)")
    p.add_argument("--label", action="append", metavar="LABEL", help="Extra label (repeatable)")
    p.set_defaults(func=cmd_add_todo)

    # move
    p = sub.add_parser("move", help="Move a card to a different list")
    p.add_argument("card_id")
    p.add_argument("--list", required=True, help="Target list: todo, doing, done")
    p.set_defaults(func=cmd_move)

    # comment
    p = sub.add_parser("comment", help="Add a comment to a card")
    p.add_argument("card_id")
    p.add_argument("--text", required=True, help="Comment text")
    p.set_defaults(func=cmd_comment)

    # label
    label_parser = sub.add_parser("label", help="Add or remove a label")
    label_sub = label_parser.add_subparsers(dest="label_command", required=True)

    p = label_sub.add_parser("add", help="Add a label to a card")
    p.add_argument("card_id")
    p.add_argument("label")
    p.set_defaults(func=cmd_label_add)

    p = label_sub.add_parser("remove", help="Remove a label from a card")
    p.add_argument("card_id")
    p.add_argument("label")
    p.set_defaults(func=cmd_label_remove)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
