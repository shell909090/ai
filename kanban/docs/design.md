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
| 完成检测 | **调度器主动**轮询 `GET /session/{id}/message?limit=1`，发现最后一条 message 的 `info.finish` 字段存在即视为 session 已结束，触发完成流程；agent **不**主动声明完成，无需 webfetch / token / 提示词注入 |
| session archived 后保留策略 | 保留 7 天审计元数据，可配置；opencode 原始会话由 opencode 自身管理 |
| 调度器部署 | 初始同机部署，要求可访问 Trello、全局 opencode server 与目标 git 仓库 |
| 作者与许可 | shell <shell909090@gmail.com>，MIT License |
| 可执行文件名 | `kanban` |
| 示例配置 | 提供 `config.example.yaml` |
| Agent model 选择 | **每个 binding 在 `bindings[].opencode.model` 必填**，自选 provider/model；调度器不内置默认，文档要求必须是 chat/instruct 模型（FIM 模型不调工具，禁用于 doing 卡） |
| opencode web session URL | URL 模式：`<opencode.base_url>/<base64url(workdir)>/session/<session_id>`。`base64url` 编码与 opencode web 自身一致（`packages/core/src/util/encode.ts:base64Encode`），Go 用 `base64.RawURLEncoding`。所有写 session id 的 comment 默认渲染为 markdown 链接，人类在 Trello 上一键直达。 |

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
  |-- Session Event Source ------- opencode server /session/{id}/message?limit=1 polling
  |-- Session Manager ----------- opencode serve HTTP API
  |-- Worktree Manager ---------- git repository
  |-- Verify Runner ------------- build/lint/unittest hooks
  |-- Merge Queue --------------- main branch
  |-- Audit Store --------------- SQLite
```

核心原则：

- Trello 是人机协作界面，卡片列是任务状态来源。
- 卡片描述是 agent 执行依据，附件只做备查。
- 每次 todo→doing 可启动或继续一个卡片 session；session 与卡片 1:N，worktree 与卡片 1:1。
- 完成检测完全由调度器主动探测 session 最后一条 message 的 `info.finish` 字段实现；agent 不主动声明完成，无需 done URL / token / 提示词注入 / 并发锁。
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
  # session URL 由 base_url + base64url(workdir) + session_id 拼接而成（见 §6.4），
  # 不需要单独的 web 前缀配置。base_url 必须从浏览器可达；如 opencode 经 reverse proxy
  # 暴露在 https://opencode.example.com/，把 base_url 改为该 URL（API 与 UI 共享）。

bindings:
  - name: "default"
    opencode:
      model:                              # 必填：binding 默认 model；card 无 model: label 时用这个
        providerID: "..."
        modelID: "..."
      allowed_models:                      # 可选；card 写 model:X label 时只能从这里挑
        - model: "opencode-go/minimax-m3"  # 完整 "providerID/modelID" 形式
          label: "model:minimax-m3"        # card 上的 label name（"model:" 前缀约定）
        - model: "stepfun/step-3.6"
          label: "model:step-3.6"
    trello:
      board_id: "..."                      # 非敏感信息写配置
      board_name: "..."                    # 可选
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
      main_path: "/path/to/repo"            # binding 默认 repo 根（绝对路径，启动时验证存在性）
      main_branch: "main"
      worktree_root: ".worktrees"
      allowed_paths:                        # 可选；card 写 proj:X label 时只能从这里挑
        - path: "/home/shell/nextcloud/agent"
          label: "proj:agent"               # 前缀 "proj:" 跟 opencode 的 project 术语对齐
        - path: "/home/shell/src/github.com/shell909090/ai"
          label: "proj:ai"

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

WorkflowEvent 是内部事件驱动架构的统一输入。查询循环、long polling、webhook、opencode `?limit=1` finish 探测、merge queue tick 都必须转换为该模型。

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

AI agent 不直接移动到 done。完成检测由调度器通过 `info.finish` 字段被动完成（见 §6.5），agent 不主动调用任何端点。

### 6.3 Scheduler

```text
run_forever() -> never
poll_once() -> void
handle_board_changes(snapshot: BoardSnapshot) -> void
handle_card_enter_doing(card: TrelloCard) -> void
handle_card_leave_doing(card: TrelloCard, to: BoardList) -> void
handle_done_to_archived(card: TrelloCard) -> void
run_finish_watcher(now: datetime) -> void
```

调度顺序：

1. 事件源采集 Trello 状态变化、opencode session 状态变化（基于 `?limit=1` 探测）和 merge queue tick。
2. 将外部变化标准化为内部事件并写入 SQLite event store。
3. 执行状态机校验。
4. 控制 doing 并发，超限卡移动回 todo 并写 comment。
5. 对新进入 doing 的 AI 卡启动 session。
6. Finish watcher 对每个 session 探测 `info.finish` 字段；存在即触发完成流程（见 §6.5）。
7. 对 archived 卡写入 merge queue。
8. 串行处理 merge queue。

Trello v1 事件源只实现可配置间隔的查询循环。事件源接口仍按可替换方式设计，但 long polling 和 webhook 延后到 v2，不进入 v1 交付范围。

### 6.4 SessionManager / OpencodeAdapter

opencode v1 适配使用全局唯一 `opencode serve` HTTP API；该 server 服务所有 binding、所有 repo path 和所有 session。该模式默认监听 `127.0.0.1:4096`，提供 OpenAPI 文档 `/doc`、全局健康检查 `/global/health`、全局事件 SSE `/global/event`、session 创建/状态/消息/diff 等接口。`opencode web` 也会启动本地 Web 服务并可设置端口/hostname/password，但与 server 模式不完全等价，因此只作为未来适配器，不作为 v1 依赖。

```text
start_or_resume(card: TrelloCard, workspace_path: string, history: CardHistory) -> SessionRecord
send_prompt(session_id: string, prompt: string) -> void
rename_session(session_id: string, title: string) -> void
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
- model：从 `bindings[].opencode.model` 读 `providerID` + `modelID`，原样塞进 `POST /session/{id}/prompt_async` 的 `model` 字段；调度器不替用户猜默认，配置缺失则 `check-config` / 启动报错（见第 1 节默认值）。实测：server 端 `opencode.json` 配不配 provider 都行——模型走全局注册表，认证走 `auth.json`，scheduler 只管透传字符串。
- title（rename）：session 创建成功后，调度器调 `rename_session(session_id, card.name)` 把 opencode 端的 session title 设为 Trello 卡片名，让 opencode web 列表与 Trello 列表一一对应。rename 是 best-effort：失败仅 log `session.rename.fail`，不阻塞发 prompt / 写 Started comment / 移 done。实现走 `PATCH /session/{session_id}?directory={workspace_path}`，body `{"title": card.name}`。

第一轮 prompt 不由调度器拼装任务正文；调度器只提供环境变量和工作目录，让 opencode 自行读取卡片上下文。修复 prompt 可由调度器构造，内容包含失败命令和日志摘要。

### 6.4.1 opencode web session URL 知识（外部约定）

> **本节是项目对 opencode 外部行为的引用，不是调度器内部设计。**
> 任何代码拼接 session URL 都必须按本节规则，否则浏览器无法直达对应会话。

opencode web 的 session 路由**没有**独立的 basePath / prefix 配置项（vite + solidjs router 都不带 base）。URL 完全由 3 段拼成：

```text
<scheme>://<host>:<port>/<base64url(workdir)>/session/<session_id>
```

`base64url` 不是 RFC 标准的 `base64url`，而是 opencode 自己的变体——**JS `btoa` 标准 base64 + 替换 `+` → `-`、`/` → `_` + 去 `=` padding**。源码在 `packages/core/src/util/encode.ts:base64Encode`：

```typescript
export function base64Encode(value: string) {
  const bytes = new TextEncoder().encode(value)
  const binary = Array.from(bytes, (b) => String.fromCharCode(b)).join("")
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "")
}
```

Go 端对应实现：

```go
import "encoding/base64"

func base64url(s string) string {
    return base64.RawURLEncoding.EncodeToString([]byte(s))
}
```

`RawURLEncoding` 与上述 JS 规则**字节级一致**（标准 base64 + URL-safe 替换 + 去 padding）。**不要**用 `URLEncoding`（带 `=` padding）或 `StdEncoding`（带 `+/`）。

使用方在 `packages/app/src/pages/layout.tsx:448`：

```typescript
const href = `/${base64Encode(directory)}/session/${props.sessionID}`
```

**实操示例**：

| workdir | base64url | 完整 URL（base=`http://opencode.home:1234`） |
|---|---|---|
| `/home/shell/tmp/kanban` | `L2hvbWUvc2hlbGwvdG1wL2thbmJhbg` | `http://opencode.home:1234/L2hvbWUvc2hlbGwvdG1wL2thbmJhbg/session/ses_xxx` |
| `/home/用户/项目` | `L2hvbWUv5rWL6K-V5Lq65a6J5bqX`（UTF-8 字节先编码再 base64） | `http://opencode.home:1234/L2hvbWUv5rWL6K-V5Lq65a6J5bqX/session/ses_xxx` |

**对调度器的影响**：

- 调度器**没有**独立 `web_url_prefix` / `web_base_url` 配置；`opencode.base_url` 与 web URL 的 scheme/host/port **共享同一份配置**。
- 调度器**复用** `OpenCodeBaseURL` + `WorkDir` 拼 URL；不引入新字段。
- 若 opencode API 走 `http://127.0.0.1:4096`、web 走 `https://opencode.example.com/` 这种 base 必须不同的部署，把 `OpenCodeBaseURL` 配成 web 可达的那一个（API 调用也走该 base，因为 v1 阶段 base 是单一来源）；v2 若 API/UI base 强制分离再考虑加 `OpenCodeWebBaseURL` 字段。
- 任何时候生成 session URL 都要走 `formatSessionRef(workdir, sessionID)` 单一函数，禁止散落拼接（避免 base64 规则被某处误改）。

**session id 在 comment 中的链接渲染**：

所有写 session id 的 comment（▶️ Started / ✅ Completed / ❌ Error）默认把 id 渲染为 markdown 链接，URL 模式：

```text
[<session_id>](<opencode.base_url>/<base64url(workdir)>/session/<session_id>)
```

Trello 端 markdown 渲染后人类一键直达 opencode web 的对应会话。`base_url` 末尾 `/` 由 `formatSessionRef` 内部归一化。
### 6.5 完成检测（基于 session finish）

完成检测完全由调度器主动探测实现——**agent 不主动调用任何端点声明结束**，无 done URL、无 token、无提示词注入、无并发锁、无 post-done cool-down。

**原理**：opencode 暴露 `GET /session/{id}/message?limit=1`，返回该 session 最后一条 message；其 `info.finish` 字段语义为"模型本轮是否已结束说话"。**字段存在即 session 已进入静态**，调度器即可触发完成流程。模型 emit `finish` 本身就是 agent 的"完成信号"——不再需要让 agent 多调一次 HTTP。

**`finish` 字段含义**（完整枚举来自 opencode 源码 `packages/llm/src/schema/ids.ts:36` 与 `packages/opencode/src/session/llm/ai-sdk.ts:21`）：

```ts
FinishReason = ["stop", "length", "tool-calls", "content-filter", "error", "unknown"]
```

`ai-sdk.ts:21` 的 `finishReason` helper 把任何不在上述枚举里的值规范化为 `"unknown"`，所以 `info.finish` 永远是这 6 个值之一。

| 值 | 含义 | scheduler 动作 |
|---|---|---|
| 字段缺失 | 模型仍在流式生成，或只有 user prompt 没有 assistant 回复 | 跳过，等下一轮 |
| `stop` | 模型本轮正常结束 | **正常完成**：先发总结 prompt（§7.7），等总结回来再走完成流程 |
| `tool-calls` | 模型本轮调用了工具，等工具返回后下一轮再继续 | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |
| `length` | 模型达到上下文长度上限 | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |
| `content-filter` | provider 内容过滤拒绝输出 | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |
| `error` | 模型本轮出错 | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |
| `unknown` | 未识别的 finish 值（`ai-sdk.ts:22` 规范化的兜底） | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |

**关键决策**：只有 `stop` 是"模型真的干完了"信号。其他 5 个值都意味着"这一轮不正常"——`tool-calls` / `unknown` 明确表示模型还会继续（opencode 在 `packages/opencode/src/session/prompt.ts:1341` 自己也把这两个值判定为"未完成"），`length` / `content-filter` / `error` 则是异常结束。向还在跑的模型（`tool-calls`）发总结 prompt 是无意义操作，对其他异常值发总结也是浪费 token 且不会得到有用信息。所以异常 finish 全部跳过后续总结，直接 done + needs-attention，让人介入调查。

**完成流程**（`stop` 走 7.7 总结 + 7.4 主体；其他 5 个值只走 7.4 主体且加 needs-attention）：

1. 写 `✅ Completed session <id>` comment
2. 若需要 worktree，确认 main 是否变化；变化则 rebase 后再验证
3. 调 VerifyRunner 跑三件套（build / lint / unittest）
4. **通过**：移动卡片到 done
5. **失败且未超重试上限**：向同 session 发修复 prompt，卡片留在 doing
   （修复 prompt 触发新一轮模型响应，新轮 `info.finish` 出现后 watcher 再次触发验证，循环 N 次）
6. **失败且超限**：移动回 todo，写失败 comment，保留 worktree
7. 若 `info.finish ∈ {length, error}`：除上述流程外，加 `needs-attention` label + 写错误 comment

**为何不用 `/session/status`**：该端点返 `Map<SessionID, SessionStatus>`，`SessionStatus.set(sessionID, { type: "idle" })` 会从 map 删掉该 session（见 `packages/opencode/src/session/status.ts:67` 与 `run-state.ts:58`）。已完成 session 在该 map 中**不存在**，跟"未启动"无法区分，watcher 无法据此判断"模型停"还是"模型还没开始"。

**为何不用 `/session/{id}` 的 `time.archived`**：opencode 不自动归档 session，`time.archived` 永远为 `null`（需人工 `POST /session/{id}/archive`）。

**为何不需要并发锁**：完成检测唯一通路就是 finish watcher（每张卡一个 `info.finish` 触发点，watcher 单线程串行处理），不再有"agent 主动调端点 vs 调度器被动探测"两条通路，无需串行化。

**为何不需要 post-done cool-down**：旧版担心"handleCardDone 已移卡但 session 还在跑"——新设计里 watcher 检测到 `finish` 存在即视为本轮结束，session 继续在跑是自然状态（agent 准备下一轮或停下来），卡片在 done 列正是预期结果。无需额外 cool-down 阶段 abort session。

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

1. 调度器检测卡片进入 doing（两条通路，行为必须一致）：
   - **Step 2**：人类手动拖到 doing 的新卡（拖之前调度器没见过的 cardID）。
   - **Step 3**：auto-promote from todo（见 §7.1.1）。
2. 两通路**共用** cap-check helper `acceptNewCard(card, total, perProject) -> (rejected bool, reason string)`：当 `total >= MaxDoingTotal` 或 `perProject[project] >= MaxDoingPerProject` 时返回 `rejected=true` + 人类可读 `reason`（格式：`at-capacity, global=N per-project=M, project=X`）。Step 3 在显式 `break` 之前调一次；Step 2 在 register 进 `cardSessions` 之前调一次。详见 §7.1.2。
3. **Step 2 拒绝路径**（cap-check 命中）：写 `⏸ 并发上限已满：<reason>` comment（comment 先写、移卡后写，确保人类在 doing 看到原因）→ `trelloMoveCard(cardID, todoID)` → log `cap.reject card=... project=... reason=...` → **不**改 `cardSessions`（避免后续 poll 误认"在历史里"）→ **不**加 `needs-attention`（与 auto-promote cap 行为对齐，用户应能自行判断下一步）。用户后续把卡再次拖到 doing 时调度器重新评估。
4. 若 label 为 `human-task`，调度器忽略该卡，不启动 session、不移动卡、不创建 worktree；只有当它进入 done/archived 相关状态时才按人工完成结果处理。
5. 若需要 worktree，创建或复用 `.worktrees/<cardId>`，分支 `card/<cardId>`；复用时 rebase main。
6. 执行 `worktree_init` 钩子；失败记录 warning，继续。
7. 写 `▶️ Started session <id>` comment。
8. 调 `SessionManager.start_or_resume`。

### 7.2 doing → todo 暂停/失败

- 人类拖回 todo：写 `⏸ Paused by user` 和 session 结束摘要；保留 session 元数据、worktree、分支。
- session 异常：调度器拖回 todo，写 `❌ Error in session <id>`；保留 worktree。
- 三件套超限：拖回 todo，写失败命令、摘要和重试次数。
- **并发上限超限**（Step 2 / Step 3 拒绝路径，详见 §7.1.2 / §7.1.1）：移回 todo，写 `⏸ 并发上限已满：<reason>` comment，**不**加 `needs-attention` label，**不**改 `cardSessions` map（保留卡在调度器视角的"未见过"状态；用户后续重拖可重新评估）。

### 7.1.1 auto-promote（todo → doing 调度器主动通路）

- 调度器每 5s 扫 todo 列，按 `MaxDoingTotal` / `MaxDoingPerProject` 评估：未超 → 调 `trelloMoveCard(cardID, doingID)` + 启动 session（与 Step 2 共享 `acceptNewCard` helper 评估 cap，详见 §7.1.2）。
- 移动失败（`trelloMoveCard` 返 error）：回滚 `cardSessions` 注册（delete 该 cardID 的 entry）+ `total--` / `perProject[project]--` + log `promote.move.fail` + 不启动 session。下次 poll 重新评估。

### 7.1.2 `acceptNewCard` helper（Step 2 / Step 3 共享的 cap check）

```text
acceptNewCard(card: TrelloCard, total: int, perProject: map<string, int>) -> (rejected: bool, reason: string)
```

- 纯函数：只读 `cfg.MaxDoingTotal` / `cfg.MaxDoingPerProject` / `card.Labels`（解析 `projectOf`），不读不写任何状态。
- 当 `total >= MaxDoingTotal` 或 `perProject[projectOf(card)] >= MaxDoingPerProject` 时 `rejected=true`，否则 `rejected=false`。
- `reason` 在 `rejected=true` 时为 `at-capacity, global=N per-project=M, project=X`（人类可读、安全 surface 到 comment 与 log）；`rejected=false` 时为空字符串。
- 调用方负责维护 `total` / `perProject`（每次成功 accept 后 `total++` / `perProject[projectOf(card)]++`），helper 不做 mutation。
- Step 3 调用约定：循环顶部 `if total >= MaxDoingTotal: break` 保留（性能优化，避免遍历整张 todo 表）；`acceptNewCard` 处理 per-project skip + 兜底 global 检查。Step 2 调用约定：每次循环调一次，rejected→拒绝路径，未 rejected→register 进 `cardSessions` + 启动 `processCard`。
- 测试：纯函数单测覆盖 global / per-project / OK 三情形；Step 2 / Step 3 集成单测覆盖"超 cap 拒绝"和"未超 cap 接受"两条路径。

### 7.3 session finish 检测

finish watcher 每 `-idle` 间隔（默认 10s）轮询所有已注册 session，对每个 session 走以下流程。**核心原则：用 `/session/{id}/message?limit=1` 读模型本轮是否已完，判据是 `info.finish` 字段是否存在；不用 `/session/status`（其返回的 map 不包含已完成的 session，语义不对）。**

1. 在 `sessionCards` 中查 `cardID`。
2. `GET /session/{id}/message?limit=1`，拿到该 session 最后一条 message。
3. 判别 `info.finish` 字段：
   - 字段缺失（流式生成中、或只有 user prompt 没有 assistant 回复）→ 跳过，等下一轮
   - 字段存在（`stop` / `tool-calls` / `length` / `error` 任一值）→ 触发完成流程（见 §7.4）

`finish` 字段含义（来自 opencode 源码 `packages/opencode/src/session/message-v2.ts`）：

- 字段不存在：模型**仍在生成**（流式输出中），watcher 必须跳过
- `stop`：模型本轮正常结束
- `tool-calls`：模型本轮调用了工具，等工具返回后下一轮再继续
- `length`：模型达到上下文长度上限
- `error`：模型本轮出错

**任何 finish 值**都意味着"模型本轮不再说话"——这就是 agent 的"完成信号"，watcher 统一触发完成流程。无需 `tool-calls` 跳过逻辑（agent 自己会在工具返回后产生新的 assistant message 和新的 `finish`）。

**为何不用 `/session/status`**：该端点返的是 `Map<SessionID, SessionStatus>`，`SessionStatus.set(sessionID, { type: "idle" })` 会从 map 删掉该 session（见 `packages/opencode/src/session/status.ts:67` 与 `run-state.ts:58`）。已完成 session 在该 map 中**不存在**，跟"未启动"无法区分。

**为何不用 `/session/{id}` 的 `time.archived`**：opencode 不自动归档 session，`time.archived` 永远为 `null`（需人工 `POST /session/{id}/archive`）。

**为何 watcher 唯一通路、无并发锁**：完成检测是单源（finish watcher 单 goroutine 串行处理），不再有"agent 主动调端点 vs 调度器被动探测"两条通路并存。`cardLocks` 已删除（详见 §6.5）。

### 7.4 finish 检测 → 验证 → done

1. finish watcher 检测到 `info.finish` 字段存在。
2. **finish == "stop"**（模型本轮正常结束）：走 §7.7 完成后总结流程。
3. **finish ∈ {tool-calls, length, content-filter, error, unknown}**（异常 finish，详见 §6.5）：跳过后续总结，直接走 7.4 主体流程 + 标 `needs-attention`。
4. 写 `✅ Completed session <id>` comment。
5. 若需要 worktree，确认 main 是否变化；变化则 rebase 后再验证。
6. 运行 build、lint、unittest（三件套）。
7. **通过**：移动卡片到 done。
8. **失败且未超重试上限**：向同 session 发修复 prompt，卡片留在 doing；
   watcher 在新轮 `info.finish` 出现后再次触发验证，循环 N 次。
9. **失败且超限**：移动回 todo，写失败 comment，保留 worktree。
10. 若 `info.finish ≠ "stop"`：除上述流程外，加 `needs-attention` label + 写错误 comment，提示人类 attach session 调查。

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

### 7.7 完成后总结（summary on stop）

本轮 `info.finish = "stop"` 出现后、卡片移 done 之前，调度器向**同一个 session** 发一个固定中文 prompt，要求模型用 140 字以内简要描述本次工作。等下一轮 `info.finish` 出现后，从最后一条 message 的 text part 提取文本，作为一条独立 comment 写入 Trello，再走原完成流程。

**作用域**：仅当首个 finish 是 `"stop"` 时触发。任何其他 finish 值（`tool-calls` / `length` / `content-filter` / `error` / `unknown`，详见 §6.5）都直接走 7.4 主体流程并加 `needs-attention`，**不**发总结 prompt——异常 finish 下模型要么还在跑（`tool-calls`），要么本轮已经不正常（`length` / `content-filter` / `error` / `unknown`），向其发总结 prompt 没有意义。

需求来源 `req.md §5.4.4`。

**目的**：人类做 done 验证时，能在 Trello 上一眼看到 agent 自述的工作内容，不必 attach 到 opencode。

**接口**：

```text
request_summary(card_id, session_id) -> error
extract_summary_text(last_message, char_limit) -> string
mark_card_finished(card_id, session_id, finish, summary) -> void
```

`sessionInfo.status` 增加 `statusSummarizing`，与现有 `statusStarted` / `statusCompleted` 并列。`statusSummarizing` 表示"已发总结 prompt，等下一轮 finish"。

**完整流程**：

1. finish watcher 检测到 `info.finish = "stop"`（其他 5 个异常值都不进总结流程，详见 §6.5）。
2. 调度器调 `ocSendPromptAsync` 发固定中文 prompt（聚焦"本次运行的*结果*"，不是任务说明）：
   ```
   请用 140 个字以内简要总结本次运行的*结果*，不是任务说明。聚焦：
   - 实际做了哪些操作（执行了哪些命令、修改/创建/查看了哪些文件）
   - 关键产出（新增/修改/删除的文件、跑通的测试、产生的数据、得到的结论）
   - 任何值得人类关注的副产品（意外发现、未完成项、需要 follow-up 的事）

   仅输出总结本身，不要任何前缀、解释、Markdown 标记。
   ```
3. 发送成功：把 `sessionInfo.status` 切到 `statusSummarizing`，记录 `summary_started_at = time.Now()` 与 `last_finish = "stop"`。
4. watcher 在后续轮询命中 `statusSummarizing` + 新 `info.finish`：
   a. 拉 session 最后一条 message
   b. 调 `extract_summary_text` 拿到 summary 字符串
   c. 调 `mark_card_finished(cardID, sessionID, last_finish, summary)` 走原完成流程
5. watcher 不会再次触发"发总结 prompt"——`statusSummarizing` 视为"等待总结"的稳定状态。

**`extract_summary_text` 纯函数**：

- 输入 `last map[string]any`（来自 `/session/{id}/message?limit=1` 的最后一条 message），`charLimit int`（`<= 0` 视为 140）。
- 遍历 `last["parts"]`：仅取 `type == "text"` 的 part 的 `text` 字段，按出现顺序拼接。
- `strings.TrimSpace` 后取前 `charLimit` 个 rune；超出末尾追加 `…`。
- 空字符串返回 `（本次会话未产生可读总结）`。
- 单独 export（`ExtractSummaryText`），便于单测与将来挪到独立文件。

**失败与边界**：

| 情形 | 调度器动作 |
|---|---|
| 首个 finish 是 `stop` 之外的任何值 | 跳过整个 §7.7 流程；走 7.4 主体 + needs-attention（详见 §6.5） |
| `request_summary` 失败（网络 / opencode 4xx/5xx） | log `finish.summary.skip reason=send-fail`；按原 7.4 流程直接 done，**不**写 Summary comment |
| 总结 prompt 收到 `info.finish ∈ {error, length, content-filter, unknown}` | summary 取 `（总结生成失败: finish=<value>）` 写 comment；走原 7.4 流程 done，**不**额外加 `needs-attention`（首个 finish 是 `stop`，任务本身已完成） |
| 总结 prompt 收到 `info.finish = tool-calls` | 视为异常（模型对总结 prompt 也调了工具），按上一行处理 |
| 等待期间 drag-out | `handle_drag_out` 沿用原 abort + icebox 路径；增 log `finish.summary.aborted reason=drag-out` |
| 等待超时（`summary_started_at` 后 ≥ 1 分钟） | log `finish.summary.timeout`；按原 7.4 流程直接 done |
| `extract_summary_text` 拿到空 | comment 写 `📝 Summary: （本次会话未产生可读总结）` |

**comment 格式**：

```text
📝 Summary: <text>
```

`<text>` 为 `extract_summary_text` 返回的字符串（≤ 140 rune + 可选 `…`，或固定失败文案）。

**与原 7.4 流程的衔接**：

- `mark_card_finished` 签名扩展为 `(cardID, sessionID, finish, summary string)`。
- `summary != ""` 时先写 `📝 Summary: <summary>` comment，再写 `✅ Completed session <id>` comment。
- 幂等性保持：状态机仍按"status != statusStarted && status != statusSummarizing → no-op"判定；同一卡片不会被双写。
- needs-attention 升级由首个 finish 值决定（`last_finish` 字段），与总结 prompt 的 finish 解耦。首个 finish 若是 `stop` 之外的任何值，调度器在第一次 `checkOneSession` 就直接走 `mark_card_finished` 并升级 needs-attention，不会进入 `statusSummarizing` 中间态。

## 8. 评论与事件格式

调度器/AI 事件 comment 采用固定前缀。`<session-id>` 默认渲染为 markdown 链接 `[<session-id>](<base_url>/<base64url(workdir)>/session/<session-id>)`，人类在 Trello 上一键直达 opencode web 会话。`Summary: <text>` 来自模型对 §7.7 总结 prompt 的回复，聚焦"本次运行的结果"。

```text
▶️ Started session <session-id>
目标：<summary>
Workspace：<path-or-main>

📝 Summary: <text>

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
- **Card-driven 配置走 allowlist + fail-fast**：card 可在 label 声明 `proj:X`（路径） / `model:X`（model），但调度器严格按以下规则：
  - 无 label：binding 默认（`repo.main_path` / `opencode.model`）
  - 单 label 命中 allowlist：用该值
  - 单 label 不在 allowlist：**FAIL**（不静默回退）
  - 同类型多 label（多 `proj:*` 或多 `model:*`）：**FAIL**
  - FAIL 动作：写 comment 到卡说明（具体 label 值 + 冲突原因）+ 加 `needs-attention` label + **不启动 session**。卡留在 doing 等人修。
- 调度器**绝不**从 card description / comment 文本里读路径或 model——只有 `labels[]` 字段是配置源。
- 路径 / model 字符串启动时验证：路径必须 `filepath.Abs` 通过且 `os.Stat` 存在；model 必须是 `<providerID>/<modelID>` 形式（`/` 分隔，无路径分隔符）。
- 即使 allowlist 命中，路径再过 `filepath.Clean` + `..` 检测——防 allowlist 配置被改坏。

## 10. 测试设计要点

单元测试覆盖：

- 状态机合法/非法转移。
- label 行为：`human-task`、`no-worktree`、`needs-attention`、`needs-integration-test`。
- finish 检测触发完成、verify 失败重试、超限回 todo；error/length finish 加 needs-attention。
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
| 1 | 5.2、6.1、6.4、6.5、7.1、7.4 |
| 2 | 5.2、6.2、6.6、7.2 |
| 3 | 5.3、6.1、6.6 |
| 4 | 6.5、6.7、7.4 |
| 5 | 5.2、6.4、7.1 |
| 6 | 5.4、6.5、6.8 |
| 7 | 5.4、6.1、6.8 |
| 8 | 6.5、7.3 |
| 9 | 5.1、5.6、8 |
| 10 | 5.9、6.9 |
| 11 | 6.6、7.6 |
| 12 | 5.2、6.2 |
| 13 | 2、6.3 |
| 14 | 1、6.5 |
| 15 | 6.7 |
| 16 | 5.3、6.6 |
| 17 | 5.4、6.8 |
| 18 | 5.3、6.6 |
| 19 | 6.2、7.5 |
| 20 | 6.6、6.7 |
| 21 | 5.4、6.8 |
