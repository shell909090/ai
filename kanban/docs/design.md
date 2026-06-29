# Trello Kanban Agent 设计文档

本文档描述实现设计。流程规则以 `docs/events.md` 为准；需求说明见 `docs/req.md`。

## 1. 设计目标

协调器是一个常驻进程，周期性读取 Trello 和 agent driver 状态，并维护一组内存 task。它是 Trello 与 AI coding agent 的任务桥，只做五件事：

1. 从 `todo` 启动可执行卡片。
2. 维护 `doing` list 与 task 结构的一致性。
3. 通过 agent driver 监听 session 状态。
4. 对 abort、summary 和异常情况写 comment、移动卡片、释放容量。
5. 按项目 `.kanban.yml` 调用生命周期钩子并渲染初始 prompt。

本版不内置具体工程实践。worktree、分支、依赖安装、lint、unittest、部署等由项目自己的 `.kanban.yml` 和脚本定义。Trello list 是外部信号源，task 结构是协调器的运行时事实来源。

## 2. 核心数据结构

### 2.1 Task

```text
Task {
  card_id: CardID
  session_id: string  # 启动前钩子运行阶段使用占位值 "__pending__"
  proj: string
  agent: string       # 选中的 agents 配置名
  workdir: string?    # 启动前钩子可返回，创建 session 时传给 agent，也用于当前目录推断 proj
  labels: []string    # 启动时卡片 labels 快照，后续 summary prompt 继续传给 driver
  abort: time?      # 已向 session 发送 abort 的时间
  summary: time?    # 已向 session 发送 summary prompt 的时间
}
```

约束：

- 一个 card 同时最多有一个 task。
- task 存在表示协调器认为这张卡正在由某个 agent 管理。
- `session_id == "__pending__"` 只允许存在于同步运行启动前钩子的短暂阶段；pending task 必须计入容量，避免下一轮扫描多激活任务。钩子失败必须销毁 task 并释放容量，钩子成功后必须替换为真实 session id。
- task 的 `workdir` 必须由 task 结构管理；它既是 agent session 的工作目录，也是 Control API 按当前目录推断 proj 的匹配来源。
- task 的 `labels` 必须保存启动时的卡片 label 名称快照；初始 prompt 和 summary prompt 都使用这份 labels 传给 AgentDriver，避免 `model:*`、`effort:*` 等 driver 级标签在 summary 阶段丢失。
- task 销毁时必须同步释放总容量计数和 proj 容量计数。

### 2.2 RuntimeState

```text
RuntimeState {
  tasks: map[CardID]Task
  total_count: int
  proj_count: map[proj]int
}
```

计数器只用于新任务启动判断。已经启动的 session 不因容量变化而 abort。

### 2.3 CardSnapshot

```text
type CardID string

CardSnapshot {
  id: CardID
  title: string
  description: string
  list: string
  labels: []string
}
```

协调器只依赖 list 和 labels 做调度决策。

`CardID` 是 BoardGateway 返回的、不透明的、board-scoped card 身份标识：

- 底层表示当前使用 `string`，但业务代码必须通过 `type CardID string` 表达语义边界。
- 协调器不得解析、拼接、格式校验或假设 `CardID` 的后端格式；只能把它作为 map key、日志字段，以及传回同一个 BoardGateway 的操作参数。
- `CardID` 的稳定性至少覆盖协调器进程生命周期和对应 card 生命周期。
- 如果某个后端原生 id 不是字符串，BoardGateway 实现负责把它编码为稳定字符串并在内部解码。
- 当前一个 Server 只绑定一个 BoardGateway，因此 `CardID` 不包含 backend 或 board namespace；未来如果同一进程同时管理多个 board backend，再升级为 namespaced `CardID` 或结构化 `CardRef`。

## 3. 配置

建议配置结构：

```yaml
trello:
  board_id: "..."
  lists:
    todo: "todo"
    doing: "doing"
    done: "done"
  labels:
    attention: "attention"

kanban:
  default_agent: "opencode-main"

agents:
  opencode-main:
    type: "opencode"
    base_url: "http://127.0.0.1:4096"
    workdir: "/repo/default"
    username_env: OPENCODE_SERVER_USERNAME
    password_env: OPENCODE_SERVER_PASSWORD
    default_model:
      providerID: "anthropic"
      modelID: "claude-sonnet-4"
    labels:
      model:sonnet:
        providerID: "anthropic"
        modelID: "claude-sonnet-4"
      model:gpt:
        providerID: "openai"
        modelID: "gpt-5"
  codex-local:
    type: "codex"
    command: ["codex"]

projects:
  allowed:
    - label: "proj:default"
      name: "default"
      root: "/repo/default"
      kanban_config: ".kanban.yml"
    - label: "proj:agent"
      name: "agent"
      root: "/repo/agent"
      kanban_config: ".kanban.yml"

capacity:
  total: 3
  per_project: 1

hooks:
  default_timeout: 120s
  max_output_bytes: 8192

control:
  listen: "127.0.0.1:8765"
  token_env: KANBAN_CONTROL_TOKEN

timer:
  interval: 5s
  abort_timeout: 60s
  summary_timeout: 60s
```

规则：

- 无 `proj:*` label 时卡片不归协调器处理，调度流程必须忽略该卡片。
- 存在一个可识别 `proj:*` label 时使用对应 proj。
- 解析失败、多个 proj label 或 label 不在 allowlist 中，都视为 proj 解析失败。
- proj 解析失败时，卡片移到 `done`，添加 `attention`，写 comment，不启动 session。
- 每个 allowed proj 必须提供项目根目录；`kanban_config` 默认为 `.kanban.yml`。
- 无 `agent:*` label 时使用 `kanban.default_agent`。
- 存在一个可识别 `agent:*` label 时使用对应 `agents` 配置。
- 多个 `agent:*` label、未知 agent label、默认 agent 缺失或 agent 配置不合法，都视为 agent 解析失败。
- agent 解析失败时，卡片移到 `done`，添加 `attention`，写 comment，不启动 session。
- 除 `proj:*`、`agent:*` 和协调器保留标签外，其他 label 均传给 agent driver；例如 `model:*` 的合法性和含义由具体 driver 决定。

`agents` 是具名配置字典。每个 key 是 card 可通过 `agent:<key>` 选择的配置名；每个 value 必须包含 `type` 字段。协调器只用 `type` 选择 driver，其他字段保持为 driver 私有配置并由该 driver 解释。比如 `type: opencode` 可解释 `base_url`、`username_env`、`password_env`、`default_model` 和 `labels`；未来 `type: codex` 或 `type: claude` 可以解释为命令行参数、profile、sandbox、approval 等完全不同的字段。

opencode driver 构建阶段必须校验：

- `default_model.providerID` 和 `default_model.modelID` 必填。
- `allowed_models` 中带 `label` 的条目必须同时提供 `providerID` 和 `modelID`。
- 配置非法时启动失败并返回明确错误，禁止运行时发送空模型请求。

为了兼容旧配置，实现阶段可以把历史 `opencode`/`models` 配置转换成一个内置 agent，例如 `agents.default.type=opencode`，但新文档和新配置应以 `kanban.default_agent` + `agents` 为准。

## 4. 项目 `.kanban.yml`

每个项目仓库可以提供 `.kanban.yml`。协调器读取该文件来决定项目级 prompt 渲染和生命周期钩子；如果文件不存在，则使用内置默认 prompt，且不运行项目钩子。

建议结构：

```yaml
prompt:
  # 可选。存在时完整替代内置 card 格式化方式。
  template: |
    Trello card: {{ .Card.Title }}

    Description:
    {{ .Card.Description }}

  # 可选。始终追加到最终 prompt 后面，适合补充工程约束。
  addons:
    - |
      Before starting, confirm the git working tree is clean.
    - |
      Before finishing, run lint and unittest, and fix any failures.

hooks:
  session_new:
    command: ["./scripts/kanban-session-new.sh"]
    timeout: 180s
  session_finish:
    command: ["./scripts/kanban-session-finish.sh"]
    timeout: 300s
  session_abort:
    command: ["./scripts/kanban-session-abort.sh"]
    timeout: 120s
```

### 4.1 Prompt 渲染

最终初始 prompt 由两部分组成：

1. base prompt：如果 `.kanban.yml` 提供 `prompt.template`，用该模版全量渲染；否则使用内置默认格式，包含 card title、description、url、labels、proj 和 agent。
2. addon prompt：按顺序追加 `prompt.addons` 的渲染结果；addon 不改变 card 的基础格式，只补充项目约束。

模版上下文至少包含：

```text
Card.ID
Card.Title
Card.Description
Card.URL
Card.Labels
Project.Name
Project.Label
Agent.Name
Agent.Type
```

summary prompt 仍由协调器固定发送，但必须包含“不要把密钥、token、密码、私有 URL 等敏感信息写入总结”的要求。

### 4.2 Hook 执行模型

钩子同步执行。协调器只负责启动脚本、传入上下文、读取结果和处理失败，不解释脚本内部的工程动作。

支持三个钩子：

| hook | 时机 | 失败行为 |
|---|---|---|
| `session_new` | 创建 agent session 前 | 不创建 session；移卡到 `done`，添加 `attention`，写 hook 失败 comment，销毁 pending task |
| `session_finish` | summary 完成并写完成 comment 后、移卡到 `done` 前 | 添加 `attention`，写 hook 失败 comment；仍移动到 `done` 并销毁 task |
| `session_abort` | abort finish 确认并写 abort 完成 comment 后 | 添加 `attention`，写 hook 失败 comment；仍销毁 task 并释放容量 |

每个钩子的环境变量至少包含：

```text
KANBAN_EVENT              # session_new/session_finish/session_abort
KANBAN_CARD_ID
KANBAN_CARD_TITLE
KANBAN_CARD_URL
KANBAN_PROJECT
KANBAN_PROJECT_LABEL
KANBAN_AGENT
KANBAN_AGENT_TYPE
KANBAN_SESSION_ID         # session_new 阶段为空或 "__pending__"
KANBAN_WORKDIR            # 已知工作目录；session_new 前为项目 root
KANBAN_HOOK_RESULT_FD     # 专用结果通道 fd，默认 3；钩子可写 JSON 结果
```

钩子的 stdout/stderr 只进入调试日志，并按 `hooks.max_output_bytes` 截断；默认不完整写入 Trello comment，避免泄露敏感信息。

### 4.3 Hook 结果

钩子通过专用结果通道返回结构化 JSON。不要解析 stdout 作为协议，stdout/stderr 只用于日志。

协调器启动 hook 时打开一个额外 pipe，把写端作为 fd 3 传给子进程，并设置：

```text
KANBAN_HOOK_RESULT_FD=3
```

约束：

- hook 可向 fd 3 写入一个 JSON object，写完后关闭 fd；没有返回值时可以不写。
- 协调器只读取 fd 3，不从 stdout/stderr 解析协议。
- 读取到空内容表示空结果；读取到非空但 JSON 非法视为 hook 失败。
- fd 3 的读取设置大小限制，使用 `hooks.max_output_bytes`，超过限制视为 hook 失败。
- shell 脚本示例：`printf '{"workdir":"%s"}\n' "$WORKTREE" >&3`。

`session_new` 当前支持：

```json
{
  "workdir": "/repo/.worktrees/card-123",
  "comment": "Prepared worktree card-123."
}
```

规则：

- `workdir` 可空；为空时使用项目 root 创建 agent session。
- `workdir` 必须是绝对路径，且应由项目脚本保证存在。
- 协调器不直接创建或删除 git worktree；需要 worktree 的项目在 `session_new` 中创建，在 `session_finish` 或 `session_abort` 中清理。
- `comment` 可选；协调器可以写入 Trello，但必须截断且不得包含敏感信息。项目脚本应避免输出密钥、token、密码和私有 URL。

## 5. 外部接口

### 5.1 BoardGateway

```text
type CardID string

list_cards(list_name) -> []CardSnapshot
get_card(card_id CardID) -> CardSnapshot
move_card(card_id CardID, list_name) -> void
add_comment(card_id CardID, text) -> void
add_label(card_id CardID, label_name) -> void
remove_label(card_id CardID, label_name) -> void
create_card(list_name, title, description, labels) -> CardSnapshot
```

BoardGateway 是调度核心与具体看板后端之间的抽象接口。当前生产实现是 Trello，但 scheduler 不应直接依赖 Trello HTTP API、list id、label id 或 credential。

规则：

- `list_name` 使用逻辑名，例如 `todo`、`doing`、`done`；具体后端 list id 由 BoardGateway 实现解析。
- `card_id` 使用 `CardID`；它是不透明的 board-scoped 标识，调用方不得假设其格式是 Trello card id。
- `CardSnapshot.labels` 使用 label name 数组；具体后端 label id 查询和缓存由 BoardGateway 实现处理。
- `has_label` 不作为接口方法，使用对 `CardSnapshot.labels` 的纯函数判断即可。
- 所有 comment 应简短、面向人类：说明发生了什么、是否需要人工介入。
- credential 只允许存在于具体 BoardGateway 实现内部，不得进入 hooks、agent driver、Control API response 或普通日志。

### 5.2 AgentDriver

```text
create_session(agent_name, agent_config, card, labels, workdir) -> session_id
abort_session(session_id) -> void
send_prompt(session_id, prompt, labels) -> void
session_state(session_id) -> AgentState
```

```text
AgentState {
  kind: running|finished|failed
  text: string       # 可读文本，summary 完成时写入 Trello comment
  raw_finish: string # 可选；底层 finish/status，供 comment 和日志排查
}
```

协调器只依赖 `kind` 分支，不解释底层 finish 值。具体 driver 负责把 opencode、codex、claude code 等工具的状态映射为 `running`、`finished` 或 `failed`。

opencode driver 的推荐映射：

```text
missing finish -> running
tool-calls     -> running
stop           -> finished
length         -> failed
content-filter -> failed
error          -> failed
unknown        -> failed
```

### 5.3 ProjectConfigLoader

```text
load_project_config(project) -> ProjectConfig
```

读取项目根目录下的 `.kanban.yml`。文件不存在时返回空配置；语法错误或配置非法视为 `session_new` 前置失败，卡片进入 `done` 并添加 `attention`。

### 5.4 PromptRenderer

```text
render_initial_prompt(card, project, agent, project_config) -> string
render_summary_prompt() -> string
```

`render_initial_prompt` 先渲染 base prompt，再追加 addons。`render_summary_prompt` 固定包含 140 字以内总结和敏感信息禁止写入总结的要求。

### 5.5 HookRunner

```text
run_hook(event, task, card, project, agent, workdir, project_config) -> HookResult
```

```text
HookResult {
  workdir: string?
  comment: string?
}
```

返回非零 exit code、超时、上下文取消、结果 JSON 非法或 `workdir` 非法都视为 hook 失败。

## 6. 本地控制 API 与 AI 操作脚本

为减少人工维护 Trello task 的成本，协调器提供本地控制 API，配套 Python 脚本和 skill 供 AI 使用。Trello credential 只保存在协调器侧；脚本不读取 Trello key/token。

### 6.1 Control API

默认只监听 `127.0.0.1`，认证 token 从环境变量或配置引用的 secret 文件读取。所有读写操作都必须鉴权。

建议接口：

```text
GET  /control/v1/lists
GET  /control/v1/cards?list=<todo|doing|done>
GET  /control/v1/cards/<card_id>
POST /control/v1/cards
POST /control/v1/cards/<card_id>/move
POST /control/v1/cards/<card_id>/comments
POST /control/v1/cards/<card_id>/labels
DELETE /control/v1/cards/<card_id>/labels/<label>
```

请求和响应使用 JSON。写接口至少支持：

```text
create_card(title, description, labels, list)
move_card(card_id, list)
add_comment(card_id, text)
add_label(card_id, label)
remove_label(card_id, label)
infer_project(cwd) -> project
```

规则：

- API 使用协调器已有的 Trello 配置、list 映射和 label 映射。
- 创建 AI todo 时，API 可以根据请求中的 `cwd` 推断项目：对 configured project root 和当前 task 管理的 workdir 做路径清理、绝对化和 symlink 解析，选择包含 `cwd` 的最长路径级匹配；匹配成功后自动添加该 project 的 `proj:*` label。
- 路径匹配必须按路径边界判断，禁止纯字符串前缀匹配。例如 `/repo/app2` 不能匹配 `/repo/app`。
- 如果多个 project root 或 task workdir 都匹配，最长路径胜出；如果最长路径仍有并列，返回歧义错误。
- 如果 `cwd` 不在任何 project root 或当前 task workdir 下，且请求没有显式 project override，则返回错误，不创建归 AI 管理的 todo。
- 显式 project override 必须使用项目名或配置 key，不要求脚本传 `proj:*` label；协调器负责转换成 Trello label。
- API 不暴露 Trello credential。
- API 应记录审计日志，包含操作类型、card id、目标 list/label，但不记录敏感正文。
- 对未知 list、未知 label、空 title、过长 comment 等输入返回明确错误。
- 批量修改由脚本逐条调用 API；协调器保持每个请求原子。

### 6.2 Python 脚本

仓库提供 `scripts/kanbanctl.py` 作为 AI 和人类都可使用的稳定入口。

建议命令：

```text
kanbanctl.py list-cards --list todo
kanbanctl.py show-card <card_id>
kanbanctl.py add-todo --title <title> --desc <description> --agent opencode-main
kanbanctl.py add-todo --title <title> --desc <description> --label model:sonnet
kanbanctl.py add-todo --title <title> --desc <description> --project agent
kanbanctl.py move <card_id> --list doing
kanbanctl.py comment <card_id> --text <text>
kanbanctl.py label add <card_id> <label>
kanbanctl.py label remove <card_id> <label>
```

`add-todo` 默认把 `os.getcwd()` 作为 `cwd` 传给 Control API，由协调器推断 project 并添加 `proj:*` label。`--project` 只用于显式覆盖推断结果；`--agent` 添加 `agent:*` label，未提供时由协调器使用 `kanban.default_agent`。脚本允许 `--label` 传其他非 project/agent label，例如 `model:*`；这些标签的含义由具体 agent driver 解释。不建议用 `--label proj:*` 或 `--label agent:*` 绕过显式参数校验。

脚本从环境变量读取控制 API 地址和 token，例如：

```text
KANBAN_CONTROL_URL=http://127.0.0.1:8765
KANBAN_CONTROL_TOKEN_ENV=KANBAN_CONTROL_TOKEN
```

脚本只负责参数校验、请求 API、输出结构化结果和非零退出码；不直接调用 Trello。

### 6.3 Codex skill

后续提供一个轻量 skill，例如 `kanban-board`。该 skill 的主体只保留必要流程：

- 修改 Trello 前先用 `kanbanctl.py list-cards` 或 `show-card` 查询现状。
- 新增 AI 任务时默认在项目目录内运行 `kanbanctl.py add-todo`，让协调器按当前目录推断 project 并添加 `proj:*` label。
- 批量拆分任务时逐条创建 card，标题短、description 写清验收条件。
- 移动或标记现有 card 前确认 card id，避免按标题误改。
- 只有当前目录不属于目标项目，或确实需要跨项目创建任务时，才使用 `--project` 覆盖。
- 不在 card description/comment 写入密钥、token、密码或私有 URL。

skill 可把命令示例放在 `SKILL.md`，不需要额外长文档；脚本是主要可复用资源。

## 7. Timer 主循环

每轮 timer 按固定顺序执行：

```text
tick(now):
  check_session_state(now)
  reconcile_doing(now)
  check_timeouts(now)
  promote_todo(now)
```

顺序不能随意调整：

- 先处理 session 状态，避免已完成任务继续占容量。
- doing 检查中先 out 后 in，避免容量计数错误。
- timeout 在 session 状态和 doing diff 后处理，减少误判。
- todo promotion 放最后，使用最新容量。

## 8. session 状态处理

### 8.1 状态探测

对每个 task 调用：

```text
driver.session_state(task.session_id) -> AgentState
```

处理规则：

1. `state.kind == running`：跳过。
2. task.abort 非空：写 abort 成功 comment，运行 `session_abort` 钩子；钩子失败时添加 `attention` 并写 comment；销毁 task，释放容量。
3. `state.kind == failed`：移卡到 `done`，添加 `attention`，写异常结束 comment，销毁 task，释放容量。
4. `state.kind == finished` 且 task.summary 非空：写完成 comment，把 `state.text` 写入 comment，运行 `session_finish` 钩子；钩子失败时添加 `attention` 并写 comment；移卡到 `done`，销毁 task，释放容量。
5. `state.kind == finished` 且 task.summary 为空：通过 driver 发送 summary prompt，并传入 `task.labels`，设置 `task.summary = now`。如果发送 summary prompt 失败，应把卡片移到 `done`，添加 `attention`，写 comment 说明原因，销毁 task 并释放容量。

### 8.2 summary prompt

summary prompt 固定由协调器发送。目标是让 agent 用简短文本说明本次执行结果。建议文案：

```text
请用 140 个字以内总结本次运行的结果。只输出总结本身，不要前缀、解释或 Markdown。不要包含密钥、token、密码、私有 URL 或其他敏感信息。
```

协调器假设模型会遵守 140 字要求，不额外限制“完成 comment + summary”组合后的总长度。

### 8.3 异常状态

无论异常发生在原任务阶段还是 summary 阶段，都必须：

- 移卡到 `done`。
- 添加 `attention`。
- 写 comment 说明 session 异常结束，并尽量包含 driver 返回的 `raw_finish` 或等价排查信息。
- 销毁 task 并释放容量。

## 9. doing 对账

### 9.1 输入

- 当前 task 集合。
- Trello `doing` list 中所有带 `proj:*` label 的卡片。

### 9.2 算法

```text
reconcile_doing(now):
  doing_cards = cards in doing with proj label
  task_cards = keys(tasks)

  for card_id in task_cards - doing_cards:
    handle_doing_out(card_id, now)

  for card in doing_cards - task_cards:
    handle_doing_in(card, now)
```

必须先处理 `doing.out`，再处理 `doing.in`。

### 9.3 doing.in

```text
handle_doing_in(card, now):
  proj = parse_proj(card)
  if proj missing:
    return

  if proj invalid:
    move card to done
    add attention
    comment proj parse failure
    return

  agent = parse_agent(card)
  if agent invalid:
    move card to done
    add attention
    comment agent parse failure
    return

  if capacity full for total or proj:
    move card to todo
    comment capacity full
    return

  labels = card.labels
  tasks[card.id] = Task{card_id: card.id, session_id: "__pending__", proj, agent, labels}
  total_count++
  proj_count[proj]++
  hook_result = run_hook(session_new, task, card, project, agent, project.root)
  if hook failed:
    move card to done
    add attention
    comment hook failure
    destroy pending task and decrement counters
    return

  workdir = hook_result.workdir or project.root
  prompt = render_initial_prompt(card, project, agent, project_config)
  session_id = create_session(agent, card, card.labels, workdir)
  if create_session failed:
    move card to done
    add attention
    comment session create failure with proj, agent and reason
    destroy pending task and decrement counters
    return

  send_initial_prompt(session_id, prompt, card.labels)
  if send_initial_prompt failed:
    abort_session(session_id)
    move card to done
    add attention
    comment prompt send failure with proj, agent, session id and reason
    destroy pending task and decrement counters
    return

  tasks[card.id] = Task{card_id: card.id, session_id, proj, agent, workdir, labels}
  comment session started
```

### 9.4 doing.out

```text
handle_doing_out(card_id, now):
  task = tasks[card_id]
  if task.session_id == "__pending__":
    return

  abort_session(task.session_id)
  task.abort = now
  tasks[card_id] = task
  comment abort started
```

注意：doing.out 不立即销毁 task。只有 abort 成功或 abort 超时才释放容量。`"__pending__"` task 只应出现在同步启动流程中；正常 timer 不应观察到该状态。

## 10. timeout 处理

```text
check_timeouts(now):
  for task in tasks:
    if task.abort exists and now > task.abort + abort_timeout:
      add attention
      comment abort timeout
      destroy task
      continue

    if task.summary exists and now > task.summary + summary_timeout:
      move card to done
      add attention
      comment summary timeout
      destroy task
```

`destroy task` 必须原子地：

- 从 `tasks` 删除 card。
- `total_count--`。
- `proj_count[task.proj]--`。

计数不得降到负数；若发生，应写错误日志并修正为 0。

## 11. todo promotion

```text
promote_todo(now):
  if total capacity full:
    return

  for card in todo list order:
    if card has no proj label:
      continue

    proj = parse_proj(card)
    if proj invalid:
      move card to done
      add attention
      comment proj parse failure
      continue

    agent = parse_agent(card)
    if agent invalid:
      move card to done
      add attention
      comment agent parse failure
      continue

    if proj capacity full:
      continue

    move card to doing
    handle_doing_in(card, now)

    if total capacity full:
      return
```

如果某个 card 因项目容量不足不能启动，继续检查后续 card；其他 proj 的卡片仍可启动。

## 12. Comment 建议格式

```text
Started session <session_id>.

Abort requested for session <session_id>.

Abort completed for session <session_id>.

Abort timeout for session <session_id>. Please check manually.

Task finished. Summary:
<last_message_text>

Session ended abnormally: status=<driver_status>. Please check manually.

Summary timeout. Task was moved to done, but summary did not finish in time.

Cannot start task: project label is invalid: <reason>.

Cannot start task: agent label is invalid: <reason>.

Cannot start task now: capacity is full for project <proj>.

Hook session_new failed: <reason>. Please check manually.

Hook session_finish failed: <reason>. Task was still moved to done.

Hook session_abort failed: <reason>. Task tracking was still released.

Cannot start task: failed to create session for proj <proj> with agent <agent>: <reason>. Please check manually.

Cannot start task: failed to send initial prompt for session <session_id>, proj <proj>, agent <agent>: <reason>. Session abort was requested; please check manually.
```

具体文案可调整，但必须包含人类排查所需的 session id、driver 状态或底层 finish 值、proj、agent、hook 名称和原因。hook 输出写入 comment 前必须截断，并避免包含敏感信息。

## 13. 幂等与错误处理

- timer 可能重复运行；所有操作应尽量幂等。
- 对同一个 task 重复看到 `running` 不产生副作用。
- 已设置 abort 的 task 不重复发送 abort；只等待 finish 或 timeout。
- 已设置 summary 的 task 不重复发送 summary prompt；只等待下一次 finish 或 timeout。
- `session_new` hook 只在 pending task 阶段运行一次；pending task 占用容量。失败后销毁 pending task 并释放容量，避免下一轮重复创建同一个 pending task。
- `session_finish` 和 `session_abort` hook 失败不阻止 task 销毁，避免卡片因项目脚本失败而永久占用容量。
- Trello move 或 comment 失败时应记录错误，下一轮 timer 重试安全流程。
- agent create session 失败时，必须把卡片移到 `done`、添加 `attention`、写 comment 并释放 pending task，避免 `doing.in` 循环重试。
- agent create session 成功但 send initial prompt 失败时，应尽量 abort session，并把卡片移到 `done`、添加 `attention`、写 comment、释放 pending task。
- agent create session 成功但写 task 失败时，应尽量 abort session 并写错误日志。

## 14. 测试要点

单元测试建议覆盖：

- `parse_proj`：无 proj 时跳过、合法 proj、未知 proj、多个 proj。
- `parse_agent`：默认 agent、合法 agent、未知 agent、多个 agent、agent 配置非法。
- capacity：全局满、项目满、可启动、跳过无 proj 卡片。
- `session_state`：`running`、`finished` 首次、`finished` summary 完成、`failed`。
- opencode driver 状态映射：缺失 finish、`tool-calls`、`stop`、`length`、`content-filter`、`error`、`unknown`。
- opencode driver 配置校验：缺少默认模型、allowed model 字段缺失、合法配置。
- doing 对账：先 out 后 in，容量释放后可启动新卡。
- timeout：abort 超时、summary 超时、未超时不处理。
- task 销毁：总计数和项目计数正确递减。
- `.kanban.yml`：不存在时使用默认 prompt，非法时启动失败并加 `attention`。
- prompt 渲染：全量 template 替代默认格式，addons 追加到最终 prompt，summary prompt 包含敏感信息禁止写入要求。
- hooks：`session_new` 成功返回 workdir、`session_new` 失败不创建 session、`session_finish`/`session_abort` 失败只加 `attention` 且释放 task。
- 启动失败：`CreateSession` 失败和首个 `SendPrompt` 失败都移动 `done`、添加 `attention`、写 comment、释放容量；summary prompt 发送时保留 task labels。

集成测试建议覆盖：

1. todo 卡自动进入 doing 并启动 session。
2. 卡片从 doing 被人工拖走后触发 abort，finish 后释放容量。
3. session `stop` 后发送 summary，再次 `stop` 后移动 done。
4. summary 阶段异常 finish 添加 `attention`。
5. proj 或 agent label 解析失败时移动 done 并添加 `attention`。
6. 项目通过 `session_new` hook 创建 worktree 并把 workdir 返回给 agent session。
