# Kanban — Trello Kanban Agent Workflow

A scheduler-driven workflow system that uses a Trello board as the human/AI
collaboration surface. AI agents execute tasks in isolated git worktrees, run
the three verification checks, and queue merges back to `main` on archival.

> 中文说明见 [README.cn.md](README.cn.md).

## Status

**v0 — finish-watcher scheduler shipped.** The scheduler polls the Trello
`doing` list, starts an opencode session per card, and detects session
completion by polling `info.finish` on each session's last message — no agent
signal, no done URL, no per-card locks. See `docs/tasks.md` and
`docs/design.md` for the full plan.

Currently shipped:

- `kanband` — long-running scheduler (CLI wrapper around `internal/kanban`).
- `internal/kanban` — library: Trello + opencode clients, finish watcher,
  state machine, post-completion summary on `info.finish=stop`, config
  loading.
- `scripts/connectivity-test.py` — Python smoke test for Trello and opencode
  HTTP API reachability.

When a card's opencode session finishes with `stop` (the only value that
means "the model is really done"), the scheduler asks the same session
for a 140-character summary and posts it as a `📝 Summary: <text>` comment
on the card before moving it to `done`. Any other finish value
(`length` / `tool-calls` / `content-filter` / `error` / `unknown`) skips
the summary round, posts a `❌ Error in session <id>` comment, adds the
`needs-attention` label, and moves the card to `done` for human review.

The summary prompt asks the model to describe the *result* of the run
(what was done, what was produced) rather than restating the task
description.

Every `▶️ Started` / `✅ Completed` / `❌ Error` comment includes the opencode
session id as a markdown link to the opencode web session URL, so humans
can click through from Trello. The URL is built as
`<base_url>/<base64url(workdir)>/session/<id>` — no extra config needed,
the encoding matches opencode web's own. When the scheduler creates the
session it also renames it to the Trello card title, so the opencode web
session list mirrors the Trello board.

## Requirements

- Go 1.26+
- Python 3 (for the smoke test)
- Trello API key + token (or OAuth 1.0a access token)
- An `opencode serve` instance reachable from this host

## Build

```sh
make build          # produces bin/kanband
```

## Test

`make test` runs unit tests plus the connectivity smoke test.

```sh
make test                                    # unit tests only
KANBAN_OPENCODE_URL=http://localhost:4096 \
OPENCODE_SERVER_USERNAME=user \
OPENCODE_SERVER_PASSWORD=... \
  make test                                 # unit + smoke (opencode)
```

The smoke test SKIPs any step whose credentials are missing, so it always
exits 0 in a clean checkout. With Trello creds in `.env` it exercises
`/members/me/boards`; with the opencode env vars it polls `/global/health`
until 200 or 30 s timeout.

## Run

```sh
cp .env.example .env
# edit .env: TRELLO_API_KEY, TRELLO_TOKEN, OPENCODE_SERVER_*
./bin/kanband -workdir /path/to/repo
```

Flags:

- `-workdir` (required) — absolute path to the git workdir; the opencode
  session is created here.
- `-poll` (default `5s`) — Trello poll interval.
- `-idle` (default `10s`) — finish-watcher poll interval.
- `-http` (default `127.0.0.1:8087`) — bind address for `/health`.
- `-log` — log file path (default stderr).

`SIGINT` / `SIGTERM` trigger a clean shutdown: the HTTP server is stopped,
the finish watcher exits, and the main loop returns.

## Layout

```
cmd/kanband/            # thin CLI wrapper (~80 lines)
internal/kanban/        # business logic library
  config.go             # Config, LoadConfig, .env parsing
  api.go                # Trello + opencode HTTP client methods
  finish.go             # extractFinish, isAbnormalFinish, ExtractSummaryText,
                       # FinishWatcher, requestSummary
  sessionlink.go        # formatSessionRef (session id → opencode web URL)
  poll.go               # pollOnce, processCard
  log.go                # log + writeJSON + SetLogWriter
  *_test.go             # unit tests (httptest fakes for Trello + opencode)
scripts/
  connectivity-test.py  # smoke test
docs/                   # requirements, design, tasks, review, log
Makefile
go.mod
.env.example
```

## Author & License

Author: shell <shell909090@gmail.com>
License: MIT
