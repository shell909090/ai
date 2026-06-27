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
