# Kanban — Trello Kanban Agent Workflow

A scheduler-driven workflow system that uses a Trello board as the human/AI
collaboration surface. AI agents execute tasks in isolated git worktrees, run
the three verification checks, and queue merges back to `main` on archival.

## Status

**v0 — project initialized.** See `docs/tasks.md` for the planned task list
and `docs/design.md` for the design.

Currently shipped:

- Go module skeleton (`github.com/shell909090/kanban`).
- `kanban-connectivity` CLI that end-to-end verifies the local `opencode serve`
  + Trello HTTP API.

Not yet shipped:

- The scheduler process itself (`kanban` placeholder, see T002 in tasks).

## Requirements

- Go 1.26+
- `opencode` CLI on `$PATH` (for `kanban-connectivity` start mode)
- `make`

## Build

```sh
make build          # produces bin/kanban and bin/kanban-connectivity
```

## Test

`make test` runs unit tests plus the connectivity smoke test. The connectivity
test needs `OPENCODE_SERVER_USERNAME` / `OPENCODE_SERVER_PASSWORD`; Trello
checks run only when `TRELLO_API_KEY` / `TRELLO_TOKEN` are set.

```sh
export OPENCODE_SERVER_USERNAME=user
export OPENCODE_SERVER_PASSWORD=...
make test
```

Use `SKIP_OPENCODE=1` and `KANBAN_OPENCODE_URL=http://...` to test against an
already-running `opencode serve`.

## Layout

```
cmd/
  kanban/            # scheduler (placeholder, T002)
  connectivity/      # connectivity smoke test
docs/                # requirements, design, tasks, review, log
Makefile
go.mod
.env.example
```

## Author & License

Author: shell <shell909090@gmail.com>
License: MIT (see header in source files; full text to be added in T008)
