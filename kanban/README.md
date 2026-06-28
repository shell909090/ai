# Trello Kanban Agent

A coordinator that uses a Trello board to drive [opencode](https://opencode.ai/) sessions.
Humans express tasks as Trello cards; the coordinator starts, monitors, and summarises
opencode sessions automatically.

**中文说明：** [README.cn.md](README.cn.md)

## Overview

- Cards in the **todo** list are picked up automatically when capacity allows.
- The coordinator starts an opencode session for each card, sends the card description
  as the initial prompt, and writes progress comments back to Trello.
- When the session finishes, the coordinator requests a brief summary and moves the card
  to **done**.
- Humans can drag cards out of **doing** at any time; the coordinator aborts the session.
- Labels control routing: only cards with a `proj:*` label are managed by the coordinator;
  cards without one are left untouched. `model:*` selects the opencode model.

## Requirements

- Go 1.21+
- A Trello account with API key and OAuth token
- An opencode server (`opencode serve`)

## Installation

```sh
git clone <repo>
cd kanban
make build
```

The binary is written to `bin/kanband`.

## Configuration

### `.env` (secrets — never committed to git)

```
TRELLO_API_KEY=<your-api-key>
TRELLO_TOKEN=<your-oauth-token>
OPENCODE_SERVER_USERNAME=<username>
OPENCODE_SERVER_PASSWORD=<password>
```

### `config.yaml` (non-sensitive — committed to git)

```yaml
trello:
  board_id: "<board-id>"
  lists:
    todo: "<list-id>"       # Trello list ID for the todo column
    doing: "<list-id>"      # Trello list ID for the doing column
    done: "<list-id>"       # Trello list ID for the done column
  labels:
    attention: "attention"  # Trello label name added when human review is needed

opencode:
  base_url: "http://127.0.0.1:8567"
  workdir: "/path/to/repo"    # working directory for opencode sessions
  default_model:
    providerID: "opencode-go"
    modelID: "minimax-m3"
  allowed_models:
    - label: "model:sonnet"
      providerID: "anthropic"
      modelID: "claude-sonnet-4"

projects:
  allowed:
    - label: "proj:agent"
      name: "agent"

capacity:
  total: 3
  per_project: 1

timer:
  interval: 5s
  abort_timeout: 60s
  summary_timeout: 60s
```

## Project hooks: `.kanban.yml`

Each project repository can provide a `.kanban.yml` to customise how Trello cards become
opencode prompts and to run lifecycle scripts. If the file does not exist, the coordinator
uses a built-in default prompt and skips all hooks.

```yaml
prompt:
  # Optional: fully replaces the default card-to-prompt formatting.
  template: |
    Trello card: {{ .Card.Title }}

    Description:
    {{ .Card.Description }}

  # Optional: always appended after the base prompt.
  addons:
    - "Before starting, confirm the git working tree is clean."
    - "Before finishing, run lint and unittest, and fix any failures."

hooks:
  session_new:       # runs before the opencode session is created
    command: ["./scripts/kanban-session-new.sh"]
    timeout: 180s
  session_finish:    # runs after the summary comment is written; failure adds attention
    command: ["./scripts/kanban-session-finish.sh"]
    timeout: 300s
  session_abort:     # runs after abort is confirmed; failure adds attention
    command: ["./scripts/kanban-session-abort.sh"]
    timeout: 120s
```

### Hook result channel

Hooks communicate structured results via **fd 3** (a pipe set up by the coordinator):

```sh
# Return a custom working directory from session_new:
printf '{"workdir":"%s","comment":"Worktree ready."}\n' "$WORKTREE" >&3
```

Empty fd 3 output is allowed. Non-zero exit code, timeout, invalid JSON, or a
non-absolute `workdir` all count as hook failure.

### Hook environment variables

| Variable | Value |
|---|---|
| `KANBAN_EVENT` | `session_new` / `session_finish` / `session_abort` |
| `KANBAN_CARD_ID` | Trello card ID |
| `KANBAN_CARD_TITLE` | Card title |
| `KANBAN_CARD_URL` | Card URL |
| `KANBAN_PROJECT` | Project name |
| `KANBAN_PROJECT_LABEL` | `proj:*` label |
| `KANBAN_MODEL_PROVIDER` | Model provider ID |
| `KANBAN_MODEL_NAME` | Model ID |
| `KANBAN_SESSION_ID` | Session ID (`__pending__` during `session_new`) |
| `KANBAN_WORKDIR` | Working directory |
| `KANBAN_HOOK_RESULT_FD` | Always `3` |

Hook stdout/stderr is captured for debug logging only; it is never written to Trello comments.

## Card labels

| Label | Meaning |
|---|---|
| `proj:NAME` | Marks a card as AI-managed and assigns it to a named project for capacity accounting. Cards without this label are not touched by the coordinator. |
| `model:NAME` | opencode model for this card. Uses config default if absent. |
| `attention` | Needs human review — added by coordinator on errors or timeouts. |

Only cards that carry a `proj:*` label are managed by the coordinator. Cards without one
are left untouched regardless of which list they are in.

Unknown or ambiguous `proj:*` / `model:*` labels move the card to **done** with the
`attention` label and a comment explaining the reason.

## AI-driven kanban control

The coordinator exposes a local Control API so AI assistants can query and modify Trello
cards without holding Trello credentials. The API is authenticated with a Bearer token and
listens on localhost only.

Add to your `.env`:
```
KANBAN_CONTROL_TOKEN=<random-secret>
```

Add to `config.yaml`:
```yaml
control:
  listen: "127.0.0.1:8087"
  token_env: KANBAN_CONTROL_TOKEN
```

Then use `scripts/kanbanctl.py` from a project directory. The coordinator infers the
project from the current working directory. See [`scripts/SKILL.md`](scripts/SKILL.md) for
usage guidelines.

```sh
export KANBAN_CONTROL_URL=http://127.0.0.1:8087
export KANBAN_CONTROL_TOKEN=<same-as-above>

# Query current board state
python3 scripts/kanbanctl.py list-cards --list todo

# Create a new todo (project inferred from cwd)
python3 scripts/kanbanctl.py add-todo --title "Fix login bug"

# Move and comment
python3 scripts/kanbanctl.py move <card_id> --list done
python3 scripts/kanbanctl.py comment <card_id> --text "Fixed in commit abc123."
```

## Running

```sh
# Default settings from config.yaml
./bin/kanband

# Override poll interval and capacity
./bin/kanband -poll 10s -max-total 5 -max-per-project 2

# Write logs to a file
./bin/kanband -log /var/log/kanband.log

# Custom HTTP listen address (for /health)
./bin/kanband -http 0.0.0.0:8087
```

Press Ctrl+C or send SIGTERM to shut down cleanly.

## Health check

```sh
curl http://127.0.0.1:8087/health
# {"status":"ok"}
```

## Development

```sh
make fmt        # format code
make lint       # run go vet
make build      # build binary
make unittest   # run unit tests
make test       # unittest + smoke test
```

Test coverage target: 75% overall, 50% minimum per module.

## Scheduler loop

Each timer tick runs four steps in order:

1. **check session finish** — poll every tracked session for a finish event; handle normal completion, abort confirmation, and abnormal finishes.
2. **reconcile doing** — compare task state with Trello's doing list; send abort for cards that left, start sessions for cards that arrived.
3. **check timeouts** — enforce abort and summary timeouts.
4. **promote todo** — move eligible cards from todo to doing up to the configured capacity.

## Author

Shell.Xu

## License

MIT
