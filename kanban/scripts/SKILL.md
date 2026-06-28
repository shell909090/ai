# kanban-board skill

Use `scripts/kanbanctl.py` to query and modify Trello via the kanban coordinator Control API.
The coordinator holds Trello credentials; this script never exposes them.

## Setup

```sh
export KANBAN_CONTROL_URL=http://127.0.0.1:8087
export KANBAN_CONTROL_TOKEN=<token>        # same value as KANBAN_CONTROL_TOKEN in .env
```

## Core rule: query before modifying

Always check current board state before making changes:

```sh
python3 scripts/kanbanctl.py list-cards --list todo
python3 scripts/kanbanctl.py show-card <card_id>
```

Confirm the card ID before moving or labeling — avoid acting on title alone.

## Adding tasks

Run `add-todo` from inside the project directory so the coordinator infers the project:

```sh
cd /repo/myproject
python3 scripts/kanbanctl.py add-todo \
  --title "Fix login timeout bug" \
  --desc "Reproduce with: curl ... Expected: 200. Got: 401."
```

To create tasks for a different project explicitly:

```sh
python3 scripts/kanbanctl.py add-todo \
  --title "Refactor auth module" \
  --project agent
```

## Batch task creation

Split large work into one card per distinct deliverable. Do NOT put multiple unrelated
changes into a single card:

```sh
for title in "Fix input validation" "Add error logging" "Write unit tests"; do
  python3 scripts/kanbanctl.py add-todo --title "$title"
done
```

## Moving a card

```sh
python3 scripts/kanbanctl.py move <card_id> --list doing
python3 scripts/kanbanctl.py move <card_id> --list done
```

## Comments

Comments must not contain secrets, tokens, passwords, or private URLs:

```sh
python3 scripts/kanbanctl.py comment <card_id> \
  --text "Blocked on upstream API rate limit. Retry after 1h."
```

## Labels

```sh
python3 scripts/kanbanctl.py label add <card_id> attention
python3 scripts/kanbanctl.py label remove <card_id> attention
```

## When to use `--project`

Only use `--project` when:
- Running from a directory that is not inside any configured project root, OR
- You explicitly need to create a task for a different project than the current directory.

In all other cases, omit `--project` and let the coordinator infer it from the working directory.

## What NOT to write in cards

Never put secrets, tokens, passwords, API keys, or private URLs in card titles,
descriptions, or comments. The coordinator may write card content to Trello, which
may be visible to other board members.
