# Kanban — Trello Kanban Agent 工作流

一个由调度器驱动的工作流系统，把 Trello 看板作为人类与 AI agent 协作的界面。
AI agent 在隔离的 git worktree 中执行任务，跑过三件套验证后，串行合并回 `main`。

> English readme: [README.md](README.md).

## 当前状态

**v0 — finish-watcher 调度器已交付**。调度器轮询 Trello `doing` 列，为每张卡片
开一个 opencode session；通过轮询 session 最后一条 message 的 `info.finish` 字段
被动检测完成——无 agent 信号、无 done URL、无 per-card 锁。完整规划见
`docs/tasks.md` 与 `docs/design.md`。

已交付：

- `kanband` —— 长跑调度器（`internal/kanban` 库的 thin CLI 包装）
- `internal/kanban` —— 业务逻辑库：Trello + opencode 客户端、finish watcher、
  状态机、`info.finish=stop` 后的 140 字总结、配置加载
- `scripts/connectivity-test.py` —— Python smoke test，验证 Trello / opencode
  HTTP API 可达性

卡片 opencode session 收到 `stop`（唯一表示"模型真干完了"的值）时，
调度器会向同 session 发 140 字总结 prompt，把返回文本以 `📝 Summary: <text>`
comment 写到卡片，再移到 `done`。其他 5 个 finish 值（`length` / `tool-calls`
/ `content-filter` / `error` / `unknown`）跳过总结、发 `❌ Error in session <id>`
comment、加 `needs-attention` label，移到 `done` 等人介入。

总结 prompt 要求模型描述本次运行的*结果*（做了什么、产生了什么成果），
不重述任务说明。

每条 `▶️ Started` / `✅ Completed` / `❌ Error` comment 里的 session id 都
渲染为 markdown 链接，URL = `<base_url>/<base64url(workdir)>/session/<id>`，
与 opencode web 自身编码规则一致，无需额外配置。scheduler 创建 session
后还会把 title 设为 Trello 卡片名，让 opencode web 列表与 Trello 看板一一对应。

## 依赖

- Go 1.26+
- Python 3（跑 smoke test 用）
- Trello API key + token（或 OAuth 1.0a access token）
- 本机可达的 `opencode serve` 实例

## 构建

```sh
make build          # 产物：bin/kanband
```

## 测试

`make test` 跑单测 + smoke test。

```sh
make test                                    # 只跑单测
KANBAN_OPENCODE_URL=http://localhost:4096 \
OPENCODE_SERVER_USERNAME=user \
OPENCODE_SERVER_PASSWORD=... \
  make test                                  # 单测 + smoke（opencode）
```

smoke test 对凭据缺失的步骤一律 SKIPPED（在干净 checkout 上退出码永远 0）。
Trello 凭据在 `.env` 时实测 `/members/me/boards`；opencode 环境变量齐时
轮询 `/global/health` 直到 200 或 30 秒超时。

## 运行

```sh
cp .env.example .env
# 编辑 .env：TRELLO_API_KEY、TRELLO_TOKEN、OPENCODE_SERVER_*
./bin/kanband -workdir /path/to/repo
```

参数：

- `-workdir`（必填）—— git 仓库的绝对路径，opencode session 建在这里
- `-poll`（默认 `5s`）—— Trello 轮询间隔
- `-idle`（默认 `10s`）—— finish watcher 轮询间隔
- `-http`（默认 `127.0.0.1:8087`）—— `/health` 监听地址
- `-log` —— 日志文件路径（默认 stderr）

`SIGINT` / `SIGTERM` 触发优雅退出：HTTP server 关闭、finish watcher 退出、
主循环返回。

## 目录

```
cmd/kanband/            # thin CLI 包装（~80 行）
internal/kanban/        # 业务逻辑库
  config.go             # Config、LoadConfig、.env 解析
  api.go                # Trello + opencode HTTP 客户端方法
  finish.go             # extractFinish、isAbnormalFinish、ExtractSummaryText、
                       # FinishWatcher、requestSummary
  sessionlink.go        # formatSessionRef（session id → opencode web URL）
  poll.go               # pollOnce、processCard
  log.go                # log + writeJSON + SetLogWriter
  *_test.go             # 单测（用 httptest 替 Trello + opencode）
scripts/
  connectivity-test.py  # smoke test
docs/                   # 需求、设计、任务、评审、日志
Makefile
go.mod
.env.example
```

## 作者与许可

作者：shell <shell909090@gmail.com>
许可：MIT
