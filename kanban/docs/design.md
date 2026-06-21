# Trello Kanban Agent 工作流系统设计

## 1. 设计范围与默认决策

本设计覆盖 `docs/req.md` 中定义的 Trello 看板驱动、多 AI agent 并行执行、worktree 隔离、验证、归档合并和 human-task 流程。系统由一个独立协调器进程负责流程编排，不把 Trello 事件循环放进 opencode。

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
| 完成检测 | **协调器主动**轮询 `GET /session/{id}/message?limit=1`，发现最后一条 message 的 `info.finish` 字段存在即视为 session 已结束，触发完成流程；agent **不**主动声明完成，无需 webfetch / token / 提示词注入 |
| session archived 后保留策略 | 保留 7 天审计元数据，可配置；opencode 原始会话由 opencode 自身管理 |
| 协调器部署 | 初始同机部署，要求可访问 Trello、全局 opencode server 与目标 git 仓库 |
| 作者与许可 | shell <shell909090@gmail.com>，MIT License |
| 可执行文件名 | `kanban` |
| 示例配置 | 提供 `config.example.yaml` |
| Agent model 选择 | **`config.yaml` 的 `opencode.default_model` 必填**（每个 binding 一个，v1 是单 binding、顶层字段，未来多 binding 时该字段迁入 `bindings[i].opencode.default_model`）。自选 provider/model；协调器不内置默认。文档要求必须是 chat/instruct 模型（FIM 模型不调工具，禁用于 doing 卡）。Card 可用 `model:X` label 在 `opencode.allowed_models` allowlist 内覆盖默认 model。 |
| opencode web session URL | URL 模式：`<opencode.base_url>/<base64url(workdir)>/session/<session_id>`。`base64url` 编码与 opencode web 自身一致（`packages/core/src/util/encode.ts:base64Encode`），Go 用 `base64.RawURLEncoding`。所有写 session id 的 comment 默认渲染为 markdown 链接，人类在 Trello 上一键直达。 |

## 2. 总体架构

```text
Trello Board
  | poll/webhook
  v
Orchestrator Process (Go)              ← 协调器
  |-- Event Bus / Event Store ---- SQLite
  |-- Coordination Engine           ← list 归属 → 协调动作的决策核心（替代 StateMachine）
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

- **Trello 是协调界面，不是状态机**。卡片在 list 之间的归属变化是协调器接收的**信号**，不是状态转移。协调器对每种 list 信号承担对应的协调动作。
- **协调是双向事件驱动的闭环**：

  - 人类 / 协调器改变 list → 协调器承担协调动作（启动 / 监控 / 暂停 / 验证 / 合并）
  - opencode session 反馈（`info.finish`）→ 协调器把卡片移到对应 list

  驱动协调循环的**5 个关键事件**（Trello 端 4 个 + opencode 端 1 个，详见 §6.4）：

  - Trello 端：`todo.in` / `todo.out` / `doing.in` / `doing.out`
  - opencode 端：`session.finish`

  其他 list 归属变化（`icebox.*` / `done.*` / `archived.*`）不参与自动协调。
- 卡片描述是 agent 执行依据，附件只做备查。
- 每次"卡片进入 doing"信号可启动或继续一个卡片 session；session 与卡片 1:N，worktree 与卡片 1:1。
- 完成检测完全由协调器主动探测 session 最后一条 message 的 `info.finish` 字段实现；agent 不主动声明完成，无需 done URL / token / 提示词注入 / 并发锁。
- "卡片进入 archived"信号只由人类触发；协调器只负责触发后的合并、清理和错误卡生成。
- human-task 卡是协调器对"卡片进入 doing"信号的特殊排除——不启动 AI session，不创建 worktree。

## 3. 运行配置

配置文件使用 YAML：项目级配置 `config.yaml`（每个文件 = 一个 binding），项目验证配置 `.trello-verify`。项目提供 `config.example.yaml` 作为非敏感示例配置。敏感信息只来自环境变量或进程内存。

**v1 阶段是单 binding**（顶层结构），多 binding 是 v2 扩展。`config.yaml` 实际结构（与代码 `config.go` + `cardconfig` 一致）：

```yaml
trello:
  board_id: "..."                       # 非敏感信息写配置
  board_name: "..."                     # 可选
  api_key_env: TRELLO_API_KEY           # .env 变量名，密钥本身从 .env 读
  token_env: TRELLO_TOKEN
  lists:                                # 5 个 list 的实际名字（人类可改）
    icebox: "icebox"
    todo: "todo"
    doing: "doing"
    done: "done"
    archived: "archived"
  labels:                               # 约定 label 名字
    ai_task: "ai-task"
    human_task: "human-task"
    no_worktree: "no-worktree"
    needs_integration_test: "needs-integration-test"
    needs_attention: "needs-attention"

opencode:
  base_url: "http://localhost:4096"     # 浏览器可达；如走 reverse proxy 改为对应 URL
  username_env: OPENCODE_SERVER_USERNAME
  password_env: OPENCODE_SERVER_PASSWORD
  default_model:                        # 必填：binding 默认 model；card 无 model: label 时用这个
    providerID: "..."
    modelID: "..."
  allowed_models:                       # card `model:X` label 只能从这里挑
    - label: "model:..."                # card 上的 label 名字
      providerID: "..."
      modelID: "..."
  # session URL 由 base_url + base64url(workdir) + session_id 拼接而成（见 §6.5.1）。
  # v1 阶段 base_url 与 UI base 共享；v2 若 API/UI base 强制分离再加 opencode_web_url 字段。

repo:
  main_path: "/path/to/repo"            # binding 默认 repo 根（绝对路径，启动时验证存在）
  main_branch: "main"
  worktree_root: ".worktrees"
  allowed_paths:                        # card `proj:X` label 只能从这里挑
    - label: "proj:agent"               # card 上的 label 名字
      path: "/home/.../agent"
    - label: "proj:..."
      path: "/home/.../..."
```

**v2 扩展方向**（不在 v1 交付范围）：多 binding 时顶层 `trello` / `opencode` / `repo` 三段迁入 `bindings[i].{trello, opencode, repo}`，每个 binding 一份；server 级配置（listen addr、轮询间隔、cap、重试上限、SQLite 路径）从 v1 的环境变量/flag 迁入 `config.yaml` 的 `server` 段；`.trello-verify` 仍由项目仓库持有，不入 `config.yaml`。

敏感信息策略：Trello token、Trello API key、opencode server password、模型/provider 凭据只从环境变量或进程内存读取，不写入配置文件、SQLite、Trello comment 或日志。board id、board name、repo path、列名、label 名等非敏感绑定信息写入配置文件。

v1 阶段一个协调器进程服务一个 binding；多 binding 是 v2 扩展。opencode server 是全局配置：同一个 `opencode serve` 实例服务所有 binding、所有 repo path 和所有 session。

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

可执行文件名为 `kanban`。v1 CLI 以运行协调器为主，辅助提供配置检查和数据库初始化命令。

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

- `move_card` 调用前必须通过 `CoordinationEngine.decide_coordination_action`（见 §6.2）核对协调约束。
- 所有 AI/协调器事件 comment 使用固定前缀，便于扫描历史。
- 人类自由文本 comment 不做结构化改写。

### 6.2 CoordinationEngine（协调决策）

**本模块替代旧的 StateMachine**。它不是状态机——不维护"合法转移"规则；它只问"卡片收到 list X 的信号，协调器该做什么"。

```text
decide_coordination_action(
  card: TrelloCard,
  signal: CoordinationSignal,           # 卡片在 list 中的归属变化
  context: CoordinationContext          # 当前 session、worktree、并发、cap 等
) -> []CoordinationAction

review_card_movement(
  card: TrelloCard,
  signal: CoordinationSignal,
  actor: Actor
) -> CoordinationGuardResult            # 协调约束检查（人/AI 拖动时核对）
```

```text
CoordinationSignal =
  | card_in_icebox                         # 新卡进入 icebox（AI 苏格拉底后）
  | card_in_todo                           # 卡片移入 todo（人类审稿）
  | card_in_doing                          # 卡片移入 doing（人类拖或协调器 auto-promote）
  | card_in_done                           # 卡片移入 done（协调器验证通过后）
  | card_in_archived                       # 卡片移入 archived（人类验证后）
  | card_left_doing_to_todo                # 卡片从 doing 回到 todo
  | card_left_done_to_doing                # 卡片从 done 回到 doing

Actor = human | ai_agent | scheduler
CoordinationAction = start_session | resume_session | run_verify | move_to_done |
                    move_to_todo | enqueue_merge | spawn_human_task |
                    comment_only | ignore | reject_movement | undo_movement
CoordinationContext {
  card_sessions: map<cardID, SessionRecord>
  worktrees: map<cardID, WorktreeRecord>
  doing_total: int
  per_project_count: map<string, int>
  merge_queue_len: int
  cfg: Config
}
CoordinationGuardResult {
  allowed: bool
  reason: string
  corrective_action?: undo_movement | comment_only | ignore
}
```

**协调动作表**（按 list 归属信号 → 协调动作；不是状态转移表）：

| 信号 | 协调动作 | 触发方 | 备注 |
|---|---|---|---|
| `card_in_icebox` | 无主动作；卡片等待审稿 | — | AI 生成的候选任务 |
| `card_in_todo` | 无主动作；卡片排队 | — | 协调器在 polling 中按调度策略 auto-promote |
| `card_in_doing`（来自 todo） | 先看 label（`human-task` → ignore），再 cap-check → 启动 / 拒绝 / 跳过 | 协调器 | 详见 §7.1 |
| `card_in_doing`（来自 done） | 复用现有 worktree + 读人类评论 | 协调器 | 详见 §7.6 |
| `card_in_done` | 等待人类验证 | — | done 列只读 |
| `card_in_archived` | 入合并队列 | 协调器 | 详见 §6.9 / §7.5 |
| `card_left_doing_to_todo` | abort session / 清 in-memory 状态 / 保留 worktree | 协调器 | 详见 §7.2 |

**协调约束**（`review_card_movement` 的硬性边界）：

- **AI 不可把卡片移入 archived**：协调器收到 AI 触发的 `card_in_archived` 信号时 `undo_movement` + `comment_only` 说明。
- **AI 不可把卡片从 done 移走**：同上，undo 修正。
- **AI 不可把卡片从 done 移到 done / todo 之外的任何 list**（实际是 `card_in_done` / `card_in_done` 之外的所有信号），undo 修正。
- **人类不可跨级移动**（如 todo → done、icebox → doing）：`undo_movement` + 提示。
- **人类在 worktree 未验证前不可宣称 done**：`undo_movement`（详见 §6.8 三件套门控）。
- **human-task 卡不可触发 AI session**：`card_in_doing` 信号 + `human-task` label → ignore。

**核心差别（vs 旧 StateMachine）**：

- 旧：`validate_transition(from, to, actor) -> allowed` 询问"这次转移合不合法"。协调器对"非法"无主动作，只拒绝。
- 新：`decide_coordination_action(signal, context) -> actions` 询问"信号来了，协调器该做什么"。协调器对每种信号都承担动作（包括 ignore / undo），不只是允许或拒绝。

**AI agent 的角色**：不在信号表里作为主动方——AI 写 comment、修改 description、调用 trello 工具调卡片字段，但**不**直接触发 list 变化。完成由协调器通过 `info.finish` 字段被动检测（见 §6.6），agent 不调任何"我完成了"的端点。

### 6.3 Orchestrator（协调循环）

```text
run_forever() -> never
poll_once() -> void
handle_board_changes(snapshot: BoardSnapshot) -> []CoordinationAction
handle_card_in_doing(card: TrelloCard, from: BoardList) -> []CoordinationAction
handle_card_left_doing(card: TrelloCard, to: BoardList) -> []CoordinationAction
handle_card_in_archived(card: TrelloCard) -> []CoordinationAction
run_finish_watcher(now: datetime) -> []CoordinationAction
```

**协调循环**（每轮 `poll_once`）：

1. **信号采集**：Trello 事件源（`cards_in_*` / `cards_left_*`）、opencode 事件源（session `info.finish`）、merge queue tick、timer 全部转成 `CoordinationSignal`。
2. **上下文刷新**：更新 `cardSessions` / `worktrees` / `doing_total` / `per_project_count` 等上下文。
3. **协调决策**：对每条信号调 `CoordinationEngine.decide_coordination_action(signal, context)`，得到动作列表。
4. **约束核对**：人类 / AI 直接调 Trello 触发的 list 变化（拖卡），先过 `CoordinationEngine.review_card_movement`；违反的 `undo_movement` + 写 comment。
5. **动作执行**：按动作列表执行（启动 session、跑三件套、移卡、入合并队列、写 comment 等）。
6. **持久化**：每个动作产生的 `CoordinationAction` 落 `WorkflowEvent` 表（详见 §5.5）。
7. **合并队列**：archived 信号的协调动作 `enqueue_merge` 把卡入 merge queue；merge queue 处理循环在背景串行跑（详见 §6.9）。

Trello v1 事件源只实现可配置间隔的查询循环。事件源接口仍按可替换方式设计，但 long polling 和 webhook 延后到 v2，不进入 v1 交付范围。

### 6.4 5 个关键事件与响应逻辑

Orchestrator 是**双向事件驱动**的程序——Trello 状态变更事件和 opencode session 状态变更事件共同驱动协调循环。本节总结设计只关注的 **5 个关键事件**及其响应逻辑。

#### 6.4.1 关键事件清单

| 源 | 事件 | 含义 |
|---|---|---|
| Trello | `todo.in` | 卡片从非 todo 移入 todo（人类审稿后） |
| Trello | `todo.out` | 卡片从 todo 移出（人类拖到 doing / 协调器 auto-promote / 协调器回退） |
| Trello | `doing.in` | 卡片从非 doing 移入 doing（来自 todo 或 done） |
| Trello | `doing.out` | 卡片从 doing 移出（到 todo 或 done） |
| opencode | `session.finish` | session 最后一条 message 的 `info.finish` 字段存在 |

**为什么只关注这 5 个**：

- `icebox.*` / `done.*` / `archived.*` **不参与自动协调**——done 等待人类验证、archived 由人类触发合并、icebox 是候选入口。
- 协调器对后三者的"动作"已经包含在 `doing.out`（到 done）和 `todo.in`（人类审稿）等已涵盖的事件里——例如"卡片进入 done"不是自动动作（无 `done.in` 事件），是 `doing.out`（到 done）的后续人类动作。
- "卡片进入 archived" 同理：人类拖到 archived 是 `archived.in`，但协调器对其的响应（合并）已包含在 §6.9 / §7.5 流程里。

#### 6.4.2 事件源

- **Trello 事件源**（5s 轮询，可配置）：diff board snapshot 与上次状态，识别每张卡的 list 变化，转换为 4 个 `TrelloEvent`。v2 可换成长轮询 / webhook，接口不变。
- **opencode 事件源**（finish watcher，10s 轮询，可配置）：对每个 doing 卡片的 session `GET /session/{id}/message?limit=1`；判别 `info.finish` 字段；存在即转换为 `session.finish` 事件。

两路事件经事件总线归一化为内部 `WorkflowEvent`（详见 §5.5），送入协调循环。

#### 6.4.3 5 个事件的响应逻辑

| 事件 | 响应逻辑 | 详章节 |
|---|---|---|
| **`todo.in`** | 加入内部待调度视图（不立即启动 session）。下一轮 `poll_once` 触发 auto-promote 评估（cap-check + 调度策略）。无主动作。 | §7.1.1 |
| **`todo.out`** | 清理内部状态：从 `cardSessions` / `todoQueue` 移除该卡。若是 auto-promote 推动到 doing，`doing.in` 接管；若是人类拖走则无后续动作。写 `comment_only` 记录信号。 | §7.1 / §7.2 |
| **`doing.in`**（来自 todo） | 先看 label（`human-task` → ignore），再 cap-check → `start_session` 或 `move_to_todo` + `comment_only`。通过后建 worktree、跑 worktree_init 钩子、写 `▶️ Started` comment、调 `SessionManager.start_or_resume`。 | §7.1 |
| **`doing.in`**（来自 done） | 恢复 session：复用现有 worktree、读人类评论、调 `SessionManager.resume_session`。 | §7.6 |
| **`doing.out`**（到 todo） | abort session：调 `SessionManager.terminate`、清 in-memory 状态、保留 worktree 和分支。写 `⏸ Paused` / `❌ Error` comment。 | §7.2 |
| **`doing.out`**（到 done） | 保留 session 元数据和 worktree（人类验证用）。无主动作。 | §7.1 → §7.6 |
| **`session.finish`**（`info.finish = stop`） | 走完成后总结（§7.7）：发总结 prompt → 等下一轮 finish → 提取文本 → 写 Summary comment → 走 §7.4 三件套 → 移 done。 | §7.4 + §7.7 |
| **`session.finish`**（4 个异常值：`length` / `content-filter` / `error` / `unknown`） | 跳过后续总结：写 `❌ Error` comment + 加 `needs-attention` label + 走 §7.4 三件套 → 移 done。 | §7.4 |
| **`session.finish`**（`info.finish = tool-calls` 或字段缺失） | **跳过等下一轮**——`tool-calls` 表示模型调用工具后还会继续，字段缺失表示流式中，都不是完成信号。 | §7.3 |

#### 6.4.4 事件 → 协调动作映射

每个事件经 `CoordinationEngine.decide_coordination_action(signal, context)` 转成一组 `CoordinationAction`（详见 §6.2）：

| 事件 | CoordinationAction 序列 |
|---|---|
| `todo.in` | （无主动作；等下一轮 auto-promote 评估） |
| `todo.out` | `comment_only` |
| `doing.in`（来自 todo，带 `human-task` label） | `ignore` |
| `doing.in`（来自 todo，cap PASS） | `start_session` + `comment_only` |
| `doing.in`（来自 todo，cap 超限） | `move_to_todo` + `comment_only` |
| `doing.in`（来自 done） | `resume_session` + `comment_only` |
| `doing.out`（到 todo） | `terminate_session` + `move_to_todo` + `comment_only` |
| `doing.out`（到 done） | （无主动作；等人类验证） |
| `session.finish`（`info.finish = stop`） | `request_summary`（切到 statusSummarizing）→ 等下一轮 finish → `mark_card_finished` |
| `session.finish`（4 个异常值：`length` / `content-filter` / `error` / `unknown`） | `mark_card_finished` + 加 `needs-attention` label |
| `session.finish`（`info.finish = tool-calls` 或字段缺失） | `ignore`（不是完成信号，等下一轮） |

#### 6.4.5 关键事件 vs 完整信号（CoordinationSignal）

§6.2 `CoordinationSignal` 是更高层的语义抽象（包含所有 5 个 list 的所有方向）；§6.4 关键事件是驱动自动协调的**最小事件集合**。两者的对应关系：

- `CoordinationSignal.card_in_todo` ≡ `TrelloEvent.todo.in`
- `CoordinationSignal.card_in_doing` ≡ `TrelloEvent.doing.in`
- `CoordinationSignal.card_left_doing_to_todo` ≡ `TrelloEvent.doing.out`（到 todo 部分）
- `CoordinationSignal.card_left_done_to_doing` ≡ 内部合成（`doing.in` 的一部分）
- `CoordinationSignal.card_in_done` / `card_in_archived` / `card_in_icebox` **不进入关键事件**（无主动协调动作）
- `OpencodeEvent.session.finish` → 内部信号 `session_finished`

#### 6.4.6 完成检测的 6 值分流（session.finish 的细化）

`session.finish` 是 5 个关键事件中唯一一个需要按值细分的：`info.finish` 字段有 6 个可能值，**只有 5 个值触发完成流程**——`tool-calls` 不是完成信号：

| `info.finish` | 响应 |
|---|---|
| 字段缺失 | 跳过等下一轮（流式中） |
| `tool-calls` | **跳过等下一轮**（模型调用工具后还会继续，不是完成） |
| `stop` | 走 §7.7 总结 + §7.4 三件套 + 移 done |
| `length` | 跳过后续总结 + §7.4 三件套 + 移 done + `needs-attention`（上下文耗尽） |
| `content-filter` | 跳过后续总结 + §7.4 三件套 + 移 done + `needs-attention`（provider 拒绝） |
| `error` | 跳过后续总结 + §7.4 三件套 + 移 done + `needs-attention`（模型本轮出错） |
| `unknown` | 跳过后续总结 + §7.4 三件套 + 移 done + `needs-attention`（兜底） |

完整枚举与归一化逻辑、`ai-sdk.ts:21` 的 `finishReason` helper 详见 §6.5。

### 6.5 SessionManager / OpencodeAdapter

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
- model：协调器侧预先解析——按 card 的 `model:X` label（命中 `opencode.allowed_models`）或 `opencode.default_model` 确定（详见 §9）；SessionManager 接收解析后的 `{providerID, modelID}`，原样塞进 `POST /session/{id}/prompt_async` 的 `model` 字段。server 端 `opencode.json` 配不配 provider 都行——模型走全局注册表，认证走 `auth.json`，SessionManager 只管透传字符串。
- title（rename）：session 创建成功后，协调器调 `rename_session(session_id, card.name)` 把 opencode 端的 session title 设为 Trello 卡片名，让 opencode web 列表与 Trello 列表一一对应。rename 是 best-effort：失败仅 log `session.rename.fail`，不阻塞发 prompt / 写 Started comment / 移 done。实现走 `PATCH /session/{session_id}?directory={workspace_path}`，body `{"title": card.name}`。

第一轮 prompt 不由协调器拼装任务正文；协调器只提供环境变量和工作目录，让 opencode 自行读取卡片上下文。修复 prompt 可由协调器构造，内容包含失败命令和日志摘要。

### 6.5.1 opencode web session URL 知识（外部约定）

> **本节是项目对 opencode 外部行为的引用，不是协调器内部设计。**
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

**对协调器的影响**：

- 协调器**没有**独立 `web_url_prefix` / `web_base_url` 配置；`opencode.base_url` 与 web URL 的 scheme/host/port **共享同一份配置**。
- 协调器**复用** `OpenCodeBaseURL` + `WorkDir` 拼 URL；不引入新字段。
- 若 opencode API 走 `http://127.0.0.1:4096`、web 走 `https://opencode.example.com/` 这种 base 必须不同的部署，把 `OpenCodeBaseURL` 配成 web 可达的那一个（API 调用也走该 base，因为 v1 阶段 base 是单一来源）；v2 若 API/UI base 强制分离再考虑加 `OpenCodeWebBaseURL` 字段。
- 任何时候生成 session URL 都要走 `formatSessionRef(workdir, sessionID)` 单一函数，禁止散落拼接（避免 base64 规则被某处误改）。

**session id 在 comment 中的链接渲染**：

所有写 session id 的 comment（▶️ Started / ✅ Completed / ❌ Error）默认把 id 渲染为 markdown 链接，URL 模式：

```text
[<session_id>](<opencode.base_url>/<base64url(workdir)>/session/<session_id>)
```

Trello 端 markdown 渲染后人类一键直达 opencode web 的对应会话。`base_url` 末尾 `/` 由 `formatSessionRef` 内部归一化。
### 6.6 完成检测（基于 session finish）

完成检测完全由协调器主动探测实现——**agent 不主动调用任何端点声明结束**，无 done URL、无 token、无提示词注入、无并发锁、无 post-done cool-down。

**原理**：opencode 暴露 `GET /session/{id}/message?limit=1`，返回该 session 最后一条 message；其 `info.finish` 字段语义为"模型本轮是否已结束说话"。协调器**根据字段值分流**——不是所有字段值都触发完成流程。模型 emit `finish` 本身就是 agent 的"完成信号"——不再需要让 agent 多调一次 HTTP。

**`finish` 字段含义**（完整枚举来自 opencode 源码 `packages/llm/src/schema/ids.ts:36` 与 `packages/opencode/src/session/llm/ai-sdk.ts:21`）：

```ts
FinishReason = ["stop", "length", "tool-calls", "content-filter", "error", "unknown"]
```

`ai-sdk.ts:21` 的 `finishReason` helper 把任何不在上述枚举里的值规范化为 `"unknown"`，所以 `info.finish` 永远是这 6 个值之一。

| 值 | 含义 | 协调器动作 |
|---|---|---|
| 字段缺失 | 模型仍在流式生成，或只有 user prompt 没有 assistant 回复 | **跳过**，等下一轮 |
| `tool-calls` | 模型本轮调用了工具，等工具返回后下一轮再继续 | **跳过**，等下一轮——模型还会继续 |
| `stop` | 模型本轮正常结束 | **正常完成**：先发总结 prompt（§7.7），再走完成流程（§7.4） |
| `length` | 模型达到上下文长度上限 | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |
| `content-filter` | provider 内容过滤拒绝输出 | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |
| `error` | 模型本轮出错 | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |
| `unknown` | 未识别的 finish 值（`ai-sdk.ts:22` 规范化的兜底） | **异常完成**：跳过后续总结，直接 done + 标 `needs-attention` |

**关键决策**：

- `tool-calls` **不是完成信号**。模型调用工具后，等工具返回会继续生成下一轮 `assistant message`，那时会产生新的 `info.finish`。把 `tool-calls` 当作完成会过早停止协调器对 session 的监控。opencode 自己在 `packages/opencode/src/session/prompt.ts:1341` 也把 `tool-calls` 判定为"未完成"。
- 只有 `stop` 是"模型真的说完了"信号。其他 4 个值（`length` / `content-filter` / `error` / `unknown`）是异常结束，模型本轮不会再说话。向已经异常结束的模型发总结 prompt 是无意义操作，所以异常 finish 全部跳过后续总结，直接 done + needs-attention，让人介入调查。

**完成流程**（`stop` 走 §7.7 总结 + §7.4 主体；4 个异常 finish 只走 §7.4 主体且加 needs-attention）：

1. 写 `✅ Completed session <id>` comment
2. 若需要 worktree，确认 main 是否变化；变化则 rebase 后再验证
3. 调 VerifyRunner 跑三件套（build / lint / unittest）
4. **通过**：移动卡片到 done
5. **失败且未超重试上限**：向同 session 发修复 prompt，卡片留在 doing
   （修复 prompt 触发新一轮模型响应，新轮 `info.finish` 出现后 watcher 再次触发验证，循环 N 次）
6. **失败且超限**：移动回 todo，写失败 comment，保留 worktree
7. 若 `info.finish ∈ {length, content-filter, error, unknown}`：除上述流程外，加 `needs-attention` label + 写错误 comment

**为何不用 `/session/status`**：该端点返 `Map<SessionID, SessionStatus>`，`SessionStatus.set(sessionID, { type: "idle" })` 会从 map 删掉该 session（见 `packages/opencode/src/session/status.ts:67` 与 `run-state.ts:58`）。已完成 session 在该 map 中**不存在**，跟"未启动"无法区分，watcher 无法据此判断"模型停"还是"模型还没开始"。

**为何不用 `/session/{id}` 的 `time.archived`**：opencode 不自动归档 session，`time.archived` 永远为 `null`（需人工 `POST /session/{id}/archive`）。

**为何不需要并发锁**：完成检测唯一通路就是 finish watcher（每张卡一个 `info.finish` 触发点，watcher 单线程串行处理），不再有"agent 主动调端点 vs 协调器被动探测"两条通路，无需串行化。

**为何不需要 post-done cool-down**：旧版担心"handleCardDone 已移卡但 session 还在跑"——新设计里 watcher 检测到完成 finish 值即触发完成流程，session 继续在跑是自然状态（agent 准备下一轮或停下来），卡片在 done 列正是预期结果。无需额外 cool-down 阶段 abort session。

### 6.7 WorktreeManager

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

### 6.8 VerifyRunner / HookRunner

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

### 6.9 MergeQueue

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

### 6.10 IceboxCardCreator

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

> 关键流程章节按"list 归属信号 → 协调动作"组织。每节描述协调器收到某种 list 归属变化信号后承担的协调动作序列。

### 7.1 卡片进入 doing 的协调动作

卡片进入 doing 有两个来源：人类从 Trello 拖到 doing，或协调器自己从 todo 推过来。两种来源在协调器端看到的是同一个信号，处理逻辑基本一致——区别只在谁来移卡：人类拖卡时协调器响应，协调器主动推时它自己调 Trello。

**处理顺序**（按这个顺序逐步处理，任意一步不通过就停下）：

1. **看 label 是不是 `human-task`**。如果是——协调器忽略这张卡，不启动 session、不创建 worktree，**也不做 cap-check**。human-task 卡在 doing 是预期状态（人类直接处理），并发上限不约束它，不能被 cap-check 拖回 todo。
2. **过并发上限**。如果当前 doing 列卡片数已经超了——写"⏸ 并发上限已满"comment 解释原因，把卡片移回 todo，结束这次处理。`needs-attention` 不加——人类拖卡循环重试是正常的 cap 兜底机制。
3. **建或复用 worktree**（如果这张卡需要）。具体实现见 §6.7。
4. **跑 `worktree_init` 钩子**（项目声明的初始化脚本）。失败只记 warning，session 继续启动。
5. **启动 session**。具体实现（写 `▶️ Started` comment、改 session title、发 prompt、调 SessionManager）见 §6.5。

### 7.1.1 协调器主动推动（auto-promote）

协调器每 5s 扫一次 todo 列，对每张候选卡过 `acceptNewCard` 函数判断能否被接受。

- **接受**：先调 Trello 把卡片移到 doing，再走 §7.1 的第 3 步。
- **移卡失败**（Trello 接口返 error）：doing 计数回滚 + 不启动 session + 等下次轮询重新评估。
- **拒绝**（cap-check 不通过）：跳过这张卡，**不**主动移回 todo——它本来就在 todo，没有理由动它。下一轮再评估。

### 7.1.2 `acceptNewCard` 共享函数

人类拖卡通路和协调器主动推通路都共用这个函数做 cap-check，行为必须完全一致。

- **行为**：给定当前 doing 总数、每项目计数、配置上限，判断一张候选卡能否被接受。
- **返回**：是否被拒 + 原因字符串。被拒时格式为 `at-capacity, global=N per-project=M, project=X`（人类可读、安全 surface 到 comment 与 log）；接受时为空字符串。
- **上限**：全局 `MaxDoingTotal` 和每项目 `MaxDoingPerProject`，命中任一即拒。
- **纯函数**：只读 `cfg.MaxDoingTotal` / `cfg.MaxDoingPerProject` / 卡片 labels（解析出 `projectOf`），不读不写任何状态。调用方负责维护 `total` / `perProject` 计数（接受后自增，移卡失败时回滚）。
- **测试**：纯函数单测覆盖三种情形（全局超、每项目超、OK）；两处通路集成单测覆盖"拒绝"和"接受"路径。

### 7.2 卡片离开 doing 回到 todo 的协调动作

- **人类拖回 todo**：写"⏸ Paused by user"和 session 结束摘要。session 元数据、worktree、分支都保留，下次再拖回 doing 时可以继续。
- **session 异常**：协调器拖回 todo，写"❌ Error in session <id>"。worktree 保留，session 终止。
- **三件套超限**：协调器拖回 todo，写失败命令、摘要和重试次数。worktree 保留。
- **并发上限超限**（见 §7.1 第 2 步）：移回 todo，写"⏸ 并发上限已满"comment，不加 `needs-attention`——用户重拖再评估是正常的兜底机制。

### 7.3 session finish 信号 → 完成检测的协调动作

finish watcher 每 `-idle` 间隔（默认 10s）轮询所有已注册 session，对每个 session 走以下流程。**核心原则：用 `/session/{id}/message?limit=1` 读模型本轮是否已完，判据是 `info.finish` 字段值；不用 `/session/status`（其返回的 map 不包含已完成的 session，语义不对）。**

**判别流程**（按 info.finish 字段值分流）：

1. 拉 session 最后一条 message。
2. 看 `info.finish` 字段：
   - **字段缺失**（流式生成中、或只有 user prompt 没有 assistant 回复）→ 跳过，等下一轮
   - **`tool-calls`**（模型调用了工具，等工具返回后会继续）→ **跳过，等下一轮**——这不是完成信号，模型还会继续生成
   - **`stop`**（模型本轮正常结束）→ 触发完成流程（见 §7.4 + §7.7）
   - **`length` / `content-filter` / `error` / `unknown`**（异常结束）→ 触发完成流程（见 §7.4）+ 标 `needs-attention`

`finish` 字段的完整枚举来自 opencode 源码 `packages/llm/src/schema/ids.ts` 与 `packages/opencode/src/session/llm/ai-sdk.ts`，完整 6 个值 + 协调器动作详见 §6.5。

**关键判断**：

- `tool-calls` **不是完成信号**。模型调用工具后，等工具返回会继续生成下一轮 `assistant message`，那时会产生新的 `info.finish`。把 `tool-calls` 当作完成会过早停止协调器对 session 的监控。opencode 自己在 `packages/opencode/src/session/prompt.ts:1341` 也把 `tool-calls` 判定为"未完成"。
- 只有 `stop` 是"模型真的说完了"信号。`length` / `content-filter` / `error` / `unknown` 是异常结束，模型本轮不会再说话。

**为何不用 `/session/status`**：该端点返的是 `Map<SessionID, SessionStatus>`，`SessionStatus.set(sessionID, { type: "idle" })` 会从 map 删掉该 session（见 `packages/opencode/src/session/status.ts:67` 与 `run-state.ts:58`）。已完成 session 在该 map 中**不存在**，跟"未启动"无法区分。

**为何不用 `/session/{id}` 的 `time.archived`**：opencode 不自动归档 session，`time.archived` 永远为 `null`（需人工 `POST /session/{id}/archive`）。

**为何 watcher 唯一通路、无并发锁**：完成检测是单源（finish watcher 单 goroutine 串行处理），不再有"agent 主动调端点 vs 协调器被动探测"两条通路并存。`cardLocks` 已删除（详见 §6.6）。

### 7.4 finish 信号 → 验证 → 卡片移 done

1. finish watcher 检测到可触发完成的 finish 值（`stop` / `length` / `content-filter` / `error` / `unknown`）。**`tool-calls` 不在此列**——它已被 §7.3 跳过。
2. **finish == "stop"**（模型本轮正常结束）：先走 §7.7 完成后总结流程。
3. **finish ∈ {length, content-filter, error, unknown}**（异常 finish，详见 §6.5）：跳过后续总结，直接走 §7.4 主体流程 + 标 `needs-attention`。
4. 写 `✅ Completed session <id>` comment。
5. 若需要 worktree，确认 main 是否变化；变化则 rebase 后再验证。
6. 运行 build、lint、unittest（三件套）。
7. **通过**：移动卡片到 done。
8. **失败且未超重试上限**：向同 session 发修复 prompt，卡片留在 doing；
   watcher 在新轮 `info.finish` 出现后再次触发验证，循环 N 次。
9. **失败且超限**：移动回 todo，写失败 comment，保留 worktree。
10. 若 `info.finish ≠ "stop"`：除上述流程外，加 `needs-attention` label + 写错误 comment，提示人类 attach session 调查。

**修复 prompt 文案**（req.md §5.4.1 第 3 步规定，协调器侧固定，不依赖卡片描述）：

```
三件套失败，错误如下：<log>。请修复并重试。
```

- `<log>` 是 VerifyRunner 返回的失败命令 `stderr_tail` + `stdout_tail` 摘要，截断到固定字符数（具体阈值在实现时确定）。
- 同一个 session 复用：`PATCH /session/{id}/prompt_async?directory={workspace}`，不创建新 session。
- 失败计数器：`SessionRecord.verify_attempts` 自增；超过 `verify_retry_limit`（默认 3）则走 9。

### 7.5 卡片进入 archived（人类验证通过）的协调动作

1. 只能由人类拖动触发。
2. 若带 `needs-integration-test`，协调器要求 comment 中存在人工集成测试通过记录；缺失时写 warning comment，但不自动回滚人类动作。
3. `no-worktree` 直接标记归档处理完成。
4. 普通卡进入 merge queue。
5. 合并成功后删除 worktree，分支保留 28 天。

### 7.6 卡片从 done 回到 doing（验证不通过）的协调动作

1. 人类必须写 comment 描述问题和要求。
2. 协调器检测 done→doing 后复用现有 worktree/session。
3. 新 session/继续 session 读取全部评论和历史，按反馈继续。

### 7.7 完成后总结（summary on stop）

本轮 `info.finish = "stop"` 出现后、卡片移 done 之前，协调器向**同一个 session** 发一个固定中文 prompt，要求模型用 140 字以内简要描述本次工作。等下一轮 `info.finish` 出现后，从最后一条 message 的 text part 提取文本，作为一条独立 comment 写入 Trello，再走原完成流程。

**作用域**：仅当首个 finish 是 `"stop"` 时触发。其他 4 个异常 finish 值（`length` / `content-filter` / `error` / `unknown`，详见 §6.5）都直接走 7.4 主体流程并加 `needs-attention`，**不**发总结 prompt——异常 finish 下模型本轮已经不正常，向其发总结 prompt 没有意义。`tool-calls` 在 §7.3 已被 watcher 跳过，不会进入本节。

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

1. finish watcher 检测到 `info.finish = "stop"`（其他 4 个异常 finish 值 `length` / `content-filter` / `error` / `unknown` 都不进总结流程，详见 §6.5；`tool-calls` 已在 §7.3 跳过）。
2. 协调器调 `ocSendPromptAsync` 发固定中文 prompt（聚焦"本次运行的*结果*"，不是任务说明）：
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

| 情形 | 协调器动作 |
|---|---|
| 首个 finish 不是 `stop`（4 个异常值之一） | 跳过整个 §7.7 流程；走 §7.4 主体 + needs-attention（详见 §6.5） |
| `request_summary` 失败（网络 / opencode 4xx/5xx） | log `finish.summary.skip reason=send-fail`；按原 §7.4 流程直接 done，**不**写 Summary comment |
| 总结 prompt 的下一轮 `info.finish ∈ {error, length, content-filter, unknown}` | summary 取 `（总结生成失败: finish=<value>）` 写 comment；走原 §7.4 流程 done，**不**额外加 `needs-attention`（首个 finish 是 `stop`，任务本身已完成） |
| 总结 prompt 的下一轮 `info.finish = tool-calls` | 跳过等下一轮——与 §7.3 行为一致；如果持续不出现非 `tool-calls` finish，超时兜底处理 |
| 等待期间 drag-out | `handle_drag_out` 沿用原 abort + icebox 路径；增 log `finish.summary.aborted reason=drag-out` |
| 等待超时（`summary_started_at` 后 ≥ 1 分钟） | log `finish.summary.timeout`；按原 §7.4 流程直接 done |
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
- needs-attention 升级由首个 finish 值决定（`last_finish` 字段），与总结 prompt 的 finish 解耦。首个 finish 若是 `stop` 之外的任何值，协调器在第一次 `checkOneSession` 就直接走 `mark_card_finished` 并升级 needs-attention，不会进入 `statusSummarizing` 中间态。

## 8. 评论与事件格式

协调器/AI 事件 comment 采用固定前缀。`<session-id>` 默认渲染为 markdown 链接 `[<session-id>](<base_url>/<base64url(workdir)>/session/<session-id>)`，人类在 Trello 上一键直达 opencode web 会话。`Summary: <text>` 来自模型对 §7.7 总结 prompt 的回复，聚焦"本次运行的结果"。

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
- 协调器只执行项目声明的验证和钩子命令；命令输出截断后写 comment，完整日志在本地审计存储。
- AI agent 不拥有 archived 权限；human-task 不触发 AI session。
- 合并队列串行执行，避免多个卡同时修改 main。
- worktree 路径由 cardId 规范化生成，禁止路径穿越字符。
- `human-task` 由人类处理；协调器除完成态处理外忽略它，避免 AI 越权介入人工任务。
- **Card-driven 配置走 allowlist + fail-fast**：card 可在 label 声明 `proj:X`（路径） / `model:X`（model），但协调器严格按以下规则：
  - 无 label：使用 binding 默认（`repo.main_path` / `opencode.default_model`）
  - 单 label 命中 allowlist（`repo.allowed_paths` / `opencode.allowed_models`）：用该值
  - 单 label 不在 allowlist：**FAIL**（不静默回退）
  - 同类型多 label（多 `proj:*` 或多 `model:*`）：**FAIL**
  - FAIL 动作：写 comment 到卡说明（具体 label 值 + 冲突原因）+ 加 `needs-attention` label + **不启动 session**。卡留在 doing 等人修。
- 协调器**绝不**从 card description / comment 文本里读路径或 model——只有 `labels[]` 字段是配置源。
- 路径 / model 字符串启动时验证：路径必须 `filepath.Abs` 通过且 `os.Stat` 存在；model 必须是 `<providerID>/<modelID>` 形式（`/` 分隔，无路径分隔符）。
- 即使 allowlist 命中，路径再过 `filepath.Clean` + `..` 检测——防 allowlist 配置被改坏。

## 10. 测试设计要点

单元测试覆盖：

- 状态机合法/非法转移（即协调约束的允许/拒绝路径）。
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

目的：在主协调器实现之前，从本机验证 Trello HTTP API 与 `opencode serve` 都能联通，作为后续功能开发的"接地"基线。本节独立于上文的单元测试与 smoke test，是仓库初始化时一次性引入的辅助工具。

位置：`cmd/connectivity/main.go`，Go module 路径在仓库根初始化时确定（暂定 `github.com/shell909090/kanban`）。可执行文件名 `kanban-connectivity`。

依赖：仅 Go 标准库（`net/http`、`encoding/json`、`os`、`os/exec`、`time`、`context`）。不引入 Trello SDK、不连接主协调器代码、不写 SQLite、不操作 worktree。

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

复用关系：本模块是独立诊断工具，不被主协调器 import。当后续 smoke test 需要类似联通能力时，可把 HTTP 客户端、opencode 端点封装提取到 `internal/opencodeapi` 包给主协调器与本模块共用。

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
