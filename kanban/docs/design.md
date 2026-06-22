# Trello Kanban Agent 设计文档

本文档描述实现设计。流程规则以 `docs/events.md` 为准；需求说明见 `docs/req.md`。

## 1. 设计目标

协调器是一个常驻进程，周期性读取 Trello 和 opencode 状态，并维护一组内存 task。它只做四件事：

1. 从 `todo` 启动可执行卡片。
2. 维护 `doing` list 与 task 结构的一致性。
3. 监听 opencode `session.finish`。
4. 对 abort、summary 和异常情况写 comment、移动卡片、释放容量。

本版不设计复杂状态机。Trello list 是外部信号源，task 结构是协调器的运行时事实来源。

## 2. 核心数据结构

### 2.1 Task

```text
Task {
  card_id: string
  session_id: string
  proj: string
  model: ModelRef
  abort: time?      # 已向 session 发送 abort 的时间
  summary: time?    # 已向 session 发送 summary prompt 的时间
}
```

约束：

- 一个 card 同时最多有一个 task。
- task 存在表示协调器认为这张卡正在由 opencode 管理。
- task 销毁时必须同步释放总容量计数和 proj 容量计数。

### 2.2 RuntimeState

```text
RuntimeState {
  tasks: map[card_id]Task
  total_count: int
  proj_count: map[proj]int
}
```

计数器只用于新任务启动判断。已经启动的 session 不因容量变化而 abort。

### 2.3 CardSnapshot

```text
CardSnapshot {
  id: string
  title: string
  description: string
  list: string
  labels: []string
}
```

协调器只依赖 list 和 labels 做调度决策。

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
    human: "human"
    attention: "attention"

opencode:
  base_url: "http://127.0.0.1:4096"
  username_env: OPENCODE_SERVER_USERNAME
  password_env: OPENCODE_SERVER_PASSWORD

models:
  default:
    provider: "anthropic"
    model: "claude-sonnet-4"
  allowed:
    - label: "model:sonnet"
      provider: "anthropic"
      model: "claude-sonnet-4"
    - label: "model:gpt"
      provider: "openai"
      model: "gpt-5"

projects:
  default: "default"
  allowed:
    - label: "proj:default"
      name: "default"
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

规则：

- 无 `proj:*` label 时使用 `projects.default`。
- 存在一个可识别 `proj:*` label 时使用对应 proj。
- 解析失败、多个 proj label 或 label 不在 allowlist 中，都视为 proj 解析失败。
- proj 解析失败时，卡片移到 `done`，添加 `attention`，写 comment，不启动 session。
- 无 `model:*` label 时使用 `models.default`。
- 存在一个可识别 `model:*` label 时使用对应模型。
- 多个 model label、未知 model label 或配置不合法，都视为 model 解析失败。
- model 解析失败时，卡片移到 `done`，添加 `attention`，写 comment，不启动 session。

## 4. 外部接口

### 4.1 TrelloGateway

```text
list_cards(list_name) -> []CardSnapshot
move_card(card_id, list_name) -> void
add_comment(card_id, text) -> void
add_label(card_id, label_name) -> void
has_label(card, label_name) -> bool
```

所有 comment 应简短、面向人类：说明发生了什么、是否需要人工介入。

### 4.2 OpencodeGateway

```text
create_session(card, model) -> session_id
abort_session(session_id) -> void
send_summary_prompt(session_id) -> void
last_message(session_id) -> Message
```

```text
Message {
  finish: string?   # info.finish
  text: string      # 可读文本，summary 完成时写入 Trello comment
}
```

`finish` 合法值：`stop`、`tool-calls`、`length`、`content-filter`、`error`、`unknown`。缺失表示 session 仍在继续。

## 5. Timer 主循环

每轮 timer 按固定顺序执行：

```text
tick(now):
  check_session_finish(now)
  reconcile_doing(now)
  check_timeouts(now)
  promote_todo(now)
```

顺序不能随意调整：

- 先处理 finish，避免已完成任务继续占容量。
- doing 检查中先 out 后 in，避免容量计数错误。
- timeout 在 finish 和 doing diff 后处理，减少误判。
- todo promotion 放最后，使用最新容量。

## 6. session.finish 处理

### 6.1 finish 探测

对每个 task 调用：

```text
GET /session/:session_id/message?limit=1
```

处理规则：

1. `finish` 缺失或 `finish == tool-calls`：跳过。
2. task.abort 非空：写 abort 成功 comment，销毁 task，释放容量。
3. `finish != stop`：移卡到 `done`，添加 `attention`，写异常结束 comment，销毁 task，释放容量。
4. `finish == stop` 且 task.summary 非空：写完成 comment，把最后一条 message 文本写入 comment，移卡到 `done`，销毁 task，释放容量。
5. `finish == stop` 且 task.summary 为空：发送 summary prompt，设置 `task.summary = now`。

### 6.2 summary prompt

summary prompt 固定由协调器发送。目标是让 opencode 用简短文本说明本次执行结果。建议文案：

```text
请用 140 个字以内总结本次运行的结果。只输出总结本身，不要前缀、解释或 Markdown。
```

协调器假设模型会遵守 140 字要求，不额外限制“完成 comment + summary”组合后的总长度。

### 6.3 异常 finish

以下 finish 都视为异常：

- `length`
- `content-filter`
- `error`
- `unknown`

无论异常发生在原任务阶段还是 summary 阶段，都必须：

- 移卡到 `done`。
- 添加 `attention`。
- 写 comment 说明 session 异常结束和 finish 值。
- 销毁 task 并释放容量。

## 7. doing 对账

### 7.1 输入

- 当前 task 集合。
- Trello `doing` list 中所有非 `human` 卡片。

### 7.2 算法

```text
reconcile_doing(now):
  doing_cards = cards in doing without human label
  task_cards = keys(tasks)

  for card_id in task_cards - doing_cards:
    handle_doing_out(card_id, now)

  for card in doing_cards - task_cards:
    handle_doing_in(card, now)
```

必须先处理 `doing.out`，再处理 `doing.in`。

### 7.3 doing.in

```text
handle_doing_in(card, now):
  proj = parse_proj(card)
  if proj invalid:
    move card to done
    add attention
    comment proj parse failure
    return

  model = parse_model(card)
  if model invalid:
    move card to done
    add attention
    comment model parse failure
    return

  if capacity full for total or proj:
    move card to todo
    comment capacity full
    return

  session_id = create_session(card, model)
  tasks[card.id] = Task{card_id: card.id, session_id, proj, model}
  total_count++
  proj_count[proj]++
  comment session started
```

### 7.4 doing.out

```text
handle_doing_out(card_id, now):
  task = tasks[card_id]
  abort_session(task.session_id)
  task.abort = now
  tasks[card_id] = task
  comment abort started
```

注意：doing.out 不立即销毁 task。只有 abort 成功或 abort 超时才释放容量。

## 8. timeout 处理

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

## 9. todo promotion

```text
promote_todo(now):
  if total capacity full:
    return

  for card in todo list order:
    if card has human label:
      continue

    proj = parse_proj(card)
    if proj invalid:
      move card to done
      add attention
      comment proj parse failure
      continue

    model = parse_model(card)
    if model invalid:
      move card to done
      add attention
      comment model parse failure
      continue

    if proj capacity full:
      continue

    move card to doing
    handle_doing_in(card, now)

    if total capacity full:
      return
```

如果某个 card 因项目容量不足不能启动，继续检查后续 card；其他 proj 的卡片仍可启动。

## 10. Comment 建议格式

```text
Started session <session_id>.

Abort requested for session <session_id>.

Abort completed for session <session_id>.

Abort timeout for session <session_id>. Please check manually.

Task finished. Summary:
<last_message_text>

Session ended abnormally: finish=<finish>. Please check manually.

Summary timeout. Task was moved to done, but summary did not finish in time.

Cannot start task: project label is invalid: <reason>.

Cannot start task: model label is invalid: <reason>.

Cannot start task now: capacity is full for project <proj>.
```

具体文案可调整，但必须包含人类排查所需的 session id、finish 值、proj、model 和原因。

## 11. 幂等与错误处理

- timer 可能重复运行；所有操作应尽量幂等。
- 对同一个 task 重复看到 `tool-calls` 不产生副作用。
- 已设置 abort 的 task 不重复发送 abort；只等待 finish 或 timeout。
- 已设置 summary 的 task 不重复发送 summary prompt；只等待下一次 finish 或 timeout。
- Trello move 或 comment 失败时应记录错误，下一轮 timer 重试安全流程。
- opencode create session 成功但写 task 失败时，应尽量 abort session 并写错误日志。

## 12. 测试要点

单元测试建议覆盖：

- `parse_proj`：默认 proj、合法 proj、未知 proj、多个 proj。
- `parse_model`：默认 model、合法 model、未知 model、多个 model。
- capacity：全局满、项目满、可启动、跳过 human。
- `session.finish`：缺失、`tool-calls`、`stop` 首次、`stop` summary 完成、4 种异常 finish。
- doing 对账：先 out 后 in，容量释放后可启动新卡。
- timeout：abort 超时、summary 超时、未超时不处理。
- task 销毁：总计数和项目计数正确递减。

集成测试建议覆盖：

1. todo 卡自动进入 doing 并启动 session。
2. 卡片从 doing 被人工拖走后触发 abort，finish 后释放容量。
3. session `stop` 后发送 summary，再次 `stop` 后移动 done。
4. summary 阶段异常 finish 添加 `attention`。
5. proj 或 model label 解析失败时移动 done 并添加 `attention`。
