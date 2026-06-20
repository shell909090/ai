# Trello Kanban Agent 工作流系统设计

## 1. 设计范围与默认决策

本设计覆盖 `docs/req.md` 中定义的 Trello 看板驱动、多 AI agent 并行执行、worktree 隔离、验证、归档合并和 human-task 流程。系统由一个独立调度器进程负责流程编排，不把 Trello 事件循环放进 opencode。

默认值：

| 项 | 默认值 |
|---|---|
| 主语言 | Go |
| 本地持久化 | SQLite |
| 事件架构 | 内部事件总线；Trello、opencode、merge queue 等都转换为事件 |
| Trello 事件来源 | v1 仅实现查询循环；webhook/long polling 保留到 v2 |
| Trello 轮询间隔 | 5 秒，可配置 |
| doing 并发上限 | 3，可配置 |
| 验证失败重试上限 | 3，可配置 |
| session idle 超时 | 30 分钟，可配置 |
| `worktree_init` 钩子超时 | 10 分钟，可配置 |
| worktree 分支保留时长 | 28 天，可配置 |
| 附件命名 | `<card-id>-<stage>-<timestamp>.md` |
| opencode 集成 | 全局唯一 `opencode serve` HTTP Server；保留 `opencode web` 适配扩展点 |
| MCP `card_done` | 轻量 Python bridge，转发给 Go 调度器主进程 |
| session archived 后保留策略 | 保留 7 天审计元数据，可配置；opencode 原始会话由 opencode 自身管理 |
| 调度器部署 | 初始同机部署，要求可访问 Trello、全局 opencode server 与目标 git 仓库 |
| 作者与许可 | shell <shell909090@gmail.com>，MIT License |
| 可执行文件名 | `kanban` |
| 示例配置 | 提供 `config.example.yaml` |

## 2. 总体架构

```text
Trello Board
  | poll/webhook
  v
Scheduler Process (Go)
  |-- Event Bus / Event Store ---- SQLite
  |-- Board State Machine
  |-- Concurrency Controller
  |-- Trello Event Source -------- poll / long-poll / webhook adapter
  |-- Trello Gateway
  |-- Session Event Source ------- opencode server SSE/status adapter
  |-- Session Manager ----------- opencode serve HTTP API
  |-- MCP Bridge (Python) ------- card_done -> Scheduler HTTP callback
  |-- Worktree Manager ---------- git repository
  |-- Verify Runner ------------- build/lint/unittest hooks
  |-- Merge Queue --------------- main branch
  |-- Audit Store --------------- SQLite
```

核心原则：

- Trello 是人机协作界面，卡片列是任务状态来源。
- 卡片描述是 agent 执行依据，附件只做备查。
- 每次 todo→doing 可启动或继续一个卡片 session；session 与卡片 1:N，worktree 与卡片 1:1。
- `card_done` 是 agent 完成信号，不直接移动卡片；调度器验证通过后移动到 done。
- done→archived 只由人类触发；调度器只负责触发后的合并、清理和错误卡生成。
- human-task 卡不启动 AI session，不创建 worktree。

## 3. 运行配置

配置文件使用 YAML：全局配置为 `config.yaml`，项目验证配置为 `.trello-verify`。项目提供 `config.example.yaml` 作为非敏感示例配置。敏感信息只来自环境变量或进程内存。

```yaml
server:
  listen_addr: "127.0.0.1:8087"
  trello_poll_interval_seconds: 5
  idle_timeout_seconds: 1800
  max_doing_cards: 3
  verify_retry_limit: 3
  hook_timeout_seconds: 600
  branch_retention_days: 28
  sqlite_path: "~/.local/share/kanban/orchestrator.db"

opencode:
  mode: "server"              # v1 使用全局唯一 server；未来可为 web
  base_url: "http://localhost:4096"
  username_env: OPENCODE_SERVER_USERNAME
  password_env: OPENCODE_SERVER_PASSWORD

bindings:
  - name: "default"
    trello:
      board_id: "..."          # 非敏感信息写配置
      board_name: "..."        # 可选
      api_key_env: TRELLO_API_KEY
      token_env: TRELLO_TOKEN
      lists:
        icebox: "icebox"
        todo: "todo"
        doing: "doing"
        done: "done"
        archived: "archived"
      labels:
        ai_task: "ai-task"
        human_task: "human-task"
        no_worktree: "no-worktree"
        needs_integration_test: "needs-integration-test"
        needs_attention: "needs-attention"
    repo:
      main_path: "/path/to/repo"
      main_branch: "main"
      worktree_root: ".worktrees"

verify:
  config_file: ".trello-verify"
  default_commands:
    build: "make build"
    lint: "make lint"
    unittest: "make unittest"
```

敏感信息策略：Trello token、Trello API key、opencode server password、模型/provider 凭据只从环境变量或进程内存读取，不写入配置文件、SQLite、Trello comment 或日志。board id、board name、repo path、列名、label 名等非敏感绑定信息写入配置文件。

一个调度器进程可配置多个 `bindings`，每个 binding 绑定一块 Trello board 与一个本地 repo path。事件、session、worktree、merge queue 都带 `binding_name`，不同 board/repo 之间互相隔离。opencode server 是全局配置：同一个 `opencode serve` 实例服务所有 binding、所有 repo path 和所有 session。

`.trello-verify` 项目文件结构：

```yaml
commands:
  build: "make build"
  lint: "make lint"
  unittest: "make unittest"
hooks:
  worktree_init: "./scripts/init.sh"
  pre_dev_start: "./scripts/dev-setup.sh"
```

## 4. 命令行接口

可执行文件名为 `kanban`。v1 CLI 以运行调度器为主，辅助提供配置检查和数据库初始化命令。

```text
kanban serve --config config.yaml
kanban check-config --config config.yaml
kanban init-db --config config.yaml
kanban version
```

`config.example.yaml` 必须包含多 binding 示例、全局 opencode server 示例、SQLite 默认路径和所有敏感环境变量名，但不得包含真实凭据。

## 5. 数据模型

### 5.1 TrelloCard

```text
TrelloCard {
  id: string
  short_id: string
  title: string
  description: string
  list: BoardList
  labels: set<string>
  comments: Comment[]
  attachments: Attachment[]
  updated_at: datetime
}

BoardList = icebox | todo | doing | done | archived
```

### 5.2 SessionRecord

```text
SessionRecord {
  id: string
  card_id: string
  opencode_session_id: string
  status: starting | running | idle | completed_signal | paused | error | terminated
  started_at: datetime
  last_activity_at: datetime
  ended_at: datetime?
  done_signal_count: int
  verify_attempts: int
  last_todo_snapshot: string?
  last_error: string?
}
```

说明：卡片 archived、永久回 todo 或异常终止会结束当前 session record；同一卡片再次进入 doing 可创建新 record，也可 attach/continue opencode 已保留的会话，具体由 `SessionManager.resume_or_start` 封装。

### 5.3 WorktreeRecord

```text
WorktreeRecord {
  card_id: string
  branch: string              # card/<cardId>
  path: string                # <repo>/.worktrees/<cardId>
  base_main_commit: string
  last_rebased_main_commit: string
  status: absent | active | merge_pending | merged | retained_branch | cleanup_failed
  created_at: datetime
  merged_at: datetime?
  retained_until: datetime?
}
```

### 5.4 MergeJob

```text
MergeJob {
  id: string
  card_id: string
  archived_at: datetime
  status: queued | merging | conflict_ai_merge | blocked_human_task | merged | failed
  source_branch: string
  target_branch: string
  attempts: int
  last_error: string?
  human_task_card_id: string?
}
```

### 5.5 WorkflowEvent

```text
WorkflowEvent {
  id: string
  binding_name: string
  source: trello | opencode | mcp | merge_queue | timer
  type: string
  occurred_at: datetime
  dedupe_key: string
  payload: object
  handled_at: datetime?
  handle_error: string?
}
```

WorkflowEvent 是内部事件驱动架构的统一输入。查询循环、long polling、webhook、opencode SSE、MCP bridge 都必须转换为该模型。

### 5.6 AuditEvent

```text
AuditEvent {
  id: string
  time: datetime
  binding_name: string
  card_id: string?
  session_id: string?
  type: string
  payload: object
}
```

AuditEvent 存入本地 SQLite，Trello comment 只记录面向人类的关键事件，避免把大量日志刷进卡片。

## 6. 模块接口

### 6.1 TrelloGateway

```text
get_board_snapshot() -> BoardSnapshot
get_card(card_id: string) -> TrelloCard
list_comments(card_id: string, since?: datetime) -> Comment[]
list_attachments(card_id: string) -> Attachment[]
move_card(card_id: string, to_list: BoardList, reason: string) -> void
create_card(list: BoardList, title: string, description: string, labels: string[]) -> TrelloCard
add_comment(card_id: string, body: string) -> Comment
upload_attachment(card_id: string, filename: string, mime: string, content: bytes) -> Attachment
add_label(card_id: string, label: string) -> void
remove_label(card_id: string, label: string) -> void
```

约束：

- `move_card` 调用前必须通过 `StateMachine.validate_transition`。
- 所有 AI/调度器事件 comment 使用固定前缀，便于扫描历史。
- 人类自由文本 comment 不做结构化改写。

### 6.2 StateMachine

```text
validate_transition(card: TrelloCard, from: BoardList, to: BoardList, actor: Actor) -> TransitionDecision
on_transition(event: CardMovedEvent) -> WorkflowAction[]
```

```text
Actor = human | ai_agent | scheduler
TransitionDecision {
  allowed: bool
  reason: string
  corrective_action?: move_back | comment_only | ignore
}
```

合法转移：

| From | To | Actor |
|---|---|---|
| none | icebox | ai_agent |
| icebox | todo | human |
| todo | doing | human, scheduler |
| doing | done | scheduler |
| doing | todo | human, scheduler |
| done | doing | human |
| done | archived | human |

AI agent 不直接移动到 done，只能调用 `card_done`。

### 6.3 Scheduler

```text
run_forever() -> never
poll_once() -> void
handle_board_changes(snapshot: BoardSnapshot) -> void
handle_card_enter_doing(card: TrelloCard) -> void
handle_card_leave_doing(card: TrelloCard, to: BoardList) -> void
handle_done_to_archived(card: TrelloCard) -> void
handle_idle_sessions(now: datetime) -> void
```

调度顺序：

1. 事件源采集 Trello 状态变化、opencode session 状态变化、MCP bridge 回调和 merge queue tick。
2. 将外部变化标准化为内部事件并写入 SQLite event store。
3. 执行状态机校验。
4. 控制 doing 并发，超限卡移动回 todo 并写 comment。
5. 对新进入 doing 的 AI 卡启动 session。
6. 对 idle 且未 `card_done` 的 session 加 `needs-attention`。
7. 对 archived 卡写入 merge queue。
8. 串行处理 merge queue。

Trello v1 事件源只实现可配置间隔的查询循环。事件源接口仍按可替换方式设计，但 long polling 和 webhook 延后到 v2，不进入 v1 交付范围。

### 6.4 SessionManager / OpencodeAdapter

opencode v1 适配使用全局唯一 `opencode serve` HTTP API；该 server 服务所有 binding、所有 repo path 和所有 session。该模式默认监听 `127.0.0.1:4096`，提供 OpenAPI 文档 `/doc`、全局健康检查 `/global/health`、全局事件 SSE `/global/event`、session 创建/状态/消息/diff 等接口。`opencode web` 也会启动本地 Web 服务并可设置端口/hostname/password，但与 server 模式不完全等价，因此只作为未来适配器，不作为 v1 依赖。

```text
start_or_resume(card: TrelloCard, workspace_path: string, history: CardHistory) -> SessionRecord
send_prompt(session_id: string, prompt: string) -> void
terminate(session_id: string, reason: string) -> SessionRecord
get_status(session_id: string) -> SessionStatus
subscribe_events(binding_name: string) -> EventStream
attach_url(session_id: string) -> string
```

```text
SessionStatus {
  state: running | idle | error | terminated
  last_activity_at: datetime
  error?: string
}
```

启动/恢复输入：

- workspace_path：普通卡为 worktree 路径，`no-worktree`/`human-task` 为主仓库路径或空。
- history：卡片描述、全部评论摘要、当前 todo、历史 session 事件、worktree 状态。

第一轮 prompt 不由调度器拼装任务正文；调度器只提供环境变量和工作目录，让 opencode 自行读取卡片上下文。修复 prompt 可由调度器构造，内容包含失败命令和日志摘要。

### 6.5 CardDone MCP Tool

MCP 由一个轻量 Python bridge 暴露给执行阶段 agent。Python bridge 只负责 MCP 协议适配和参数校验，然后通过本机 HTTP 回调 Go 调度器；业务状态、验证和移动卡片全部在 Go 主进程中完成。

```text
tool: card_done
input:
  card_id: string
  session_id: string
  summary: string
  todo_state: string
  dev_url?: string
output:
  accepted: bool
  verify_started: bool
  message: string
```

处理流程：

1. 校验 `session_id` 属于 `card_id` 且卡片在 doing。
2. 记录 `completed_signal`。
3. 追加 `✅ Completed session <id>` comment，包含 summary、todo_state、dev_url。
4. 调用 VerifyRunner。
5. 通过：清除 `needs-attention`，移动卡片到 done。
6. 失败且未超重试上限：向同 session 发送修复 prompt，卡片留在 doing。
7. 失败且超限：移动回 todo，写失败 comment，保留 worktree。

### 6.6 WorktreeManager

```text
needs_worktree(card: TrelloCard) -> bool
ensure_worktree(card: TrelloCard) -> WorktreeRecord
rebase_to_main(record: WorktreeRecord) -> RebaseResult
remove_worktree(card_id: string) -> void
schedule_branch_cleanup(card_id: string, retained_until: datetime) -> void
cleanup_expired_branches(now: datetime) -> CleanupResult[]
```

规则：

- `human-task` 永远不创建 worktree。
- `no-worktree` 跳过创建、合并、清理。
- 普通卡首次 doing 基于当前 main HEAD 创建 `card/<cardId>`。
- 复用 worktree 时先 rebase 当前 main；done 前若 main 已变化，再 rebase 并重新验证。
- archived 合并成功后立即删除 worktree，分支保留 28 天。

### 6.7 VerifyRunner / HookRunner

```text
load_verify_config(workspace_path: string) -> VerifyConfig
run_hook(workspace_path: string, hook_name: worktree_init | pre_dev_start) -> HookResult
run_three_checks(workspace_path: string) -> VerifyResult
```

```text
VerifyResult {
  ok: bool
  build: CommandResult
  lint: CommandResult
  unittest: CommandResult
  started_at: datetime
  ended_at: datetime
}

CommandResult {
  command: string
  exit_code: int
  stdout_tail: string
  stderr_tail: string
  duration_ms: int
}
```

要求：

- 命令在目标 workspace 中执行。
- `worktree_init` 失败不阻止 session 启动，记录 warning 并 fallback 到主目录行为。
- 三件套失败必须阻止进入 done。
- 验证日志写 AuditEvent，Trello comment 只写摘要和关键错误尾部。

### 6.8 MergeQueue

```text
enqueue_archived_card(card: TrelloCard) -> MergeJob
process_next() -> void
merge_card(job: MergeJob) -> MergeResult
create_human_task(reason: HumanTaskReason) -> TrelloCard
```

合并流程：

1. 按 archived 时间串行取队头。
2. `no-worktree` 卡直接标记完成，不执行 git 合并。
3. 普通卡先 rebase/merge main，再运行三件套。
4. 无冲突且验证通过：合并到 main，删除 worktree，分支进入保留期。
5. git 冲突：进入 AI 自动 merge 尝试。
6. AI merge 失败或验证失败：创建 `human-task` 卡到 todo，当前 job 状态为 `blocked_human_task`，阻塞后续 job。

`human-task` 描述必须包含：冲突文件和行号、原始冲突内容、双方分支状态、main HEAD、AI 尝试过程、验证失败输出、验收标准。

### 6.9 IceboxCardCreator

```text
create_icebox_cards(request: SocraticResult) -> TrelloCard[]
upload_process_attachment(card_id: string, stage: string, markdown: string) -> Attachment
```

```text
SocraticResult {
  title: string
  cards: PlannedCard[]
  process_markdown: string
}

PlannedCard {
  title: string
  goal: string
  acceptance_criteria: string[]
  files_or_modules: string[]
  dependencies: string[]
  constraints: string[]
  labels: string[]
}
```

卡片 description 只包含结构化任务说明，不包含苏格拉底过程；过程 markdown 只在创建时上传一次。

## 7. 关键流程

### 7.1 todo → doing

1. 调度器检测卡片进入 doing。
2. 若 doing 数超过上限，移动回 todo 并评论说明。
3. 若 label 为 `human-task`，调度器忽略该卡，不启动 session、不移动卡、不创建 worktree；只有当它进入 done/archived 相关状态时才按人工完成结果处理。
4. 若需要 worktree，创建或复用 `.worktrees/<cardId>`，分支 `card/<cardId>`；复用时 rebase main。
5. 执行 `worktree_init` 钩子；失败记录 warning，继续。
6. 写 `▶️ Started session <id>` comment。
7. 调 `SessionManager.start_or_resume`。

### 7.2 doing → todo 暂停/失败

- 人类拖回 todo：写 `⏸ Paused by user` 和 session 结束摘要；保留 session 元数据、worktree、分支。
- session 异常：调度器拖回 todo，写 `❌ Error in session <id>`；保留 worktree。
- 三件套超限：拖回 todo，写失败命令、摘要和重试次数。

### 7.3 idle 未完成

1. 定期读取 session 状态。
2. `state=idle` 且未收到 `card_done`，超过阈值后加 `needs-attention`。
3. 写 `⚠️ Session <id> idle, no completion. 用 opencode attach http://localhost:4096 --session <id> 查看。`
4. 卡片保持 doing。
5. 收到 `card_done`、卡片离开 doing 或 session 终止时自动清除 label。

### 7.4 card_done → done

1. agent 调 MCP `card_done`。
2. 调度器写完成 comment。
3. 若需要 worktree，确认 main 是否变化；变化则 rebase 后再验证。
4. 运行 build、lint、unittest。
5. 通过则移动到 done。
6. 失败则给同 session 发送修复 prompt；超过上限则回 todo。

### 7.5 done → archived

1. 只能由人类拖动触发。
2. 若带 `needs-integration-test`，调度器要求 comment 中存在人工集成测试通过记录；缺失时写 warning comment，但不自动回滚人类动作。
3. `no-worktree` 直接标记归档处理完成。
4. 普通卡进入 merge queue。
5. 合并成功后删除 worktree，分支保留 28 天。

### 7.6 done → doing 验证不通过

1. 人类必须写 comment 描述问题和要求。
2. 调度器检测 done→doing 后复用现有 worktree/session。
3. 新 session/继续 session 读取全部评论和历史，按反馈继续。

## 8. 评论与事件格式

调度器/AI 事件 comment 采用固定前缀：

```text
▶️ Started session <session-id>
目标：<summary>
Workspace：<path-or-main>

✅ Completed session <session-id>
摘要：<summary>
Todo：<todo_state>
Dev URL：<url-if-any>

⏸ Paused by user
Session：<session-id>
Todo：<todo_state>

❌ Error in session <session-id>
原因：<error-summary>

⚠️ Session <session-id> idle, no completion.
用 opencode attach http://localhost:4096 --session <session-id> 查看。
```

人类 comment 不强制格式，但 done→doing 时必须包含验证失败原因和具体要求。

## 9. 安全与权限边界

- Trello token、Trello API key、opencode password、模型/provider 凭据只通过环境变量或进程内存提供，不写入配置、SQLite、comment 或普通日志。
- 调度器只执行项目声明的验证和钩子命令；命令输出截断后写 comment，完整日志在本地审计存储。
- AI agent 不拥有 archived 权限；human-task 不触发 AI session。
- 合并队列串行执行，避免多个卡同时修改 main。
- worktree 路径由 cardId 规范化生成，禁止路径穿越字符。
- `human-task` 由人类处理；调度器除完成态处理外忽略它，避免 AI 越权介入人工任务。

## 10. 测试设计要点

单元测试覆盖：

- 状态机合法/非法转移。
- label 行为：`human-task`、`no-worktree`、`needs-attention`、`needs-integration-test`。
- `card_done` 成功、失败重试、超限回 todo。
- worktree 创建/复用/rebase/清理命令编排。
- `.trello-verify` 读取、钩子失败 fallback、三件套失败摘要。
- merge queue 串行、冲突 human-task 创建内容。
- comment 历史扫描和 session 恢复上下文。

smoke test 覆盖：

1. icebox→todo→doing→done→archived 主流程。
2. todo→doing→todo→doing 暂停恢复。
3. 两张 doing 卡并发且 worktree 隔离。
4. idle 未完成加 `needs-attention`。
5. 验证失败后同 session 修复。
6. archived 合并冲突生成位于 todo 列的 `human-task`。

### 10.1 连通性测试模块（v0 初始化阶段）

目的：在主调度器实现之前，从本机验证 Trello HTTP API 与 `opencode serve` 都能联通，作为后续功能开发的"接地"基线。本节独立于上文的单元测试与 smoke test，是仓库初始化时一次性引入的辅助工具。

位置：`cmd/connectivity/main.go`，Go module 路径在仓库根初始化时确定（暂定 `github.com/shell909090/kanban`）。可执行文件名 `kanban-connectivity`。

依赖：仅 Go 标准库（`net/http`、`encoding/json`、`os`、`os/exec`、`time`、`context`）。不引入 Trello SDK、不连接主调度器代码、不写 SQLite、不操作 worktree。

行为：

- 凭据来源：环境变量 `OPENCODE_SERVER_USERNAME` / `OPENCODE_SERVER_PASSWORD`（opencode 端）、`TRELLO_API_KEY` / `TRELLO_TOKEN`（Trello 端）。模块本身不读取 `.env`，由调用方/Shell 注入。
- 模式选择：
  - `SKIP_OPENCODE=1` 或 `KANBAN_OPENCODE_URL` 非空 → connect 模式：不开子进程，直接对给定 URL 验证。
  - 否则 → start 模式：子进程执行 `opencode serve --port 4096 --hostname 127.0.0.1`，日志重定向到 `/tmp/kanban-connectivity-opencode.log`。
- opencode 端验证步骤（每步独立输出 PASS/FAIL）：
  1. `/global/health` 返回 200（Basic Auth）。
  2. 创建 session（POST `/session` 或对应接口，按 opencode v1 OpenAPI），记录 `session_id`。
  3. 查询 session status，期望返回合法 JSON 且 `session_id` 匹配。
  4. 终止 session（子进程模式下额外 kill 服务进程）。
- Trello 端验证步骤：
  1. `GET https://api.trello.com/1/members/me/boards?key=<key>&token=<token>`，期望 200 + JSON 数组；只校验顶层 shape，不深入字段。
  2. 不写、不改、不创建任何 Trello 资源。
  3. `TRELLO_API_KEY` 或 `TRELLO_TOKEN` 缺失时输出 SKIPPED，不计入 FAIL。
- 输出格式：每行 JSON `{"step": "...", "result": "PASS|FAIL|SKIPPED", "detail": "..."}`；末尾打印 `SUMMARY: opencode=PASS trello=SKIPPED`。
- 退出码：0 表示无 FAIL；2 表示至少一项 FAIL。
- 超时：opencode 健康检查最长 30 秒轮询；HTTP 请求最长 10 秒。

复用关系：本模块是独立诊断工具，不被主调度器 import。当后续 smoke test 需要类似联通能力时，可把 HTTP 客户端、opencode 端点封装提取到 `internal/opencodeapi` 包给主调度器与本模块共用。

## 11. 验收标准映射

| 需求验收 | 设计位置 |
|---|---|
| 1 | 5.2、6.1、6.4、6.5 |
| 2 | 4.2、5.4、6.2、6.6 |
| 3 | 5.3、5.6、6.1 |
| 4 | 5.5、6.4 |
| 5 | 4.2、5.4、5.5 |
| 6 | 5.8、6.5 |
| 7 | 5.6、6.1、5.8 |
| 8 | 6.3 |
| 9 | 5.1、7 |
| 10 | 5.9 |
| 11 | 6.6 |
| 12 | 5.2、6.5 |
| 13 | 2、5.3 |
| 14 | 5.5 |
| 15 | 5.7 |
| 16 | 4.3、5.6 |
| 17 | 5.8 |
| 18 | 5.6 |
| 19 | 6.5 |
| 20 | 5.7、6.1 |
| 21 | 5.8、6.5 |
