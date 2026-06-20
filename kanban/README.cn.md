# Kanban — Trello Kanban Agent 工作流

一个由调度器驱动的工作流系统，把 Trello 看板作为人类与 AI agent 协作的界面。
AI agent 在隔离的 git worktree 中执行任务，跑过三件套验证后，串行合并回 `main`。

## 当前状态

**v0 — 项目已初始化**。任务清单见 `docs/tasks.md`，设计见 `docs/design.md`。

已交付：

- Go module 骨架（`github.com/shell909090/kanban`）。
- `kanban-connectivity` CLI，端到端验证本机 `opencode serve` + Trello HTTP API。

未交付：

- 调度器主进程（`kanban` 占位，见 T002）。

## 依赖

- Go 1.26+
- `opencode` CLI 需在 `$PATH` 上（`kanban-connectivity` start 模式需要）
- `make`

## 构建

```sh
make build          # 产物：bin/kanban、bin/kanban-connectivity
```

## 测试

`make test` 跑单测 + 连通性 smoke test。连通性测试需要
`OPENCODE_SERVER_USERNAME` / `OPENCODE_SERVER_PASSWORD`；Trello 检查只在
`TRELLO_API_KEY` / `TRELLO_TOKEN` 设置时执行（缺失则 SKIPPED）。

```sh
export OPENCODE_SERVER_USERNAME=user
export OPENCODE_SERVER_PASSWORD=...
make test
```

用 `SKIP_OPENCODE=1` 加 `KANBAN_OPENCODE_URL=http://...` 可以对已存在的
`opencode serve` 做联通检查，不开子进程。

## 目录

```
cmd/
  kanban/            # 调度器（占位，T002 实现）
  connectivity/      # 连通性 smoke test
docs/                # 需求、设计、任务、评审、日志
Makefile
go.mod
.env.example
```

## 作者与许可

作者：shell <shell909090@gmail.com>
许可：MIT（详细协议将在 T008 补全）
