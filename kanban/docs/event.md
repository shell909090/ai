# 5 个关键事件与触发后动作

> 协调器是双向事件驱动的程序：Trello 状态变更 + opencode session 状态变更共同驱动。本文档总结 5 个关键事件的触发后动作，与 `design.md §6.4` 对应。其他 list 归属变化（`icebox.*` / `done.*` / `archived.*`）不参与自动协调。

## 概述

5 个事件：

- Trello 端 4 个：`todo.in` / `todo.out` / `doing.in` / `doing.out`
- opencode 端 1 个：`session.finish`

每个事件经 `decide_coordination_action` 转成一组 `CoordinationAction`，协调器按序执行。

## 1. `todo.in` — 卡片进入 todo

**触发**：人类审稿通过，把卡片从 icebox 拖到 todo。

**协调器动作**：无主动作。卡片加入内部待调度视图；下一轮 `poll_once` 在 todo 列扫描时按 `acceptNewCard`（cap-check）评估是否推到 doing。

不立即启动 session——cap-check 需要扫描所有 doing 卡当前状态，单卡进入 todo 不应触发整张 doing 列表读取；auto-promote 通路每 5 秒扫一次 todo，cap-check 集中在通路顶部。

## 2. `todo.out` — 卡片离开 todo

**触发**：人类从 todo 拖回 icebox（撤回审稿）；或人类/协调器推到 doing（`doing.in` 接管）。

**协调器动作**：

- 写 `comment_only` 记录信号
- 从内部 `cardSessions` / `todoQueue` 移除该卡
- 若是 auto-promote 副作用，无需额外动作
- 若是人类拖走，停止参与 todo 调度

"卡片离开 todo"是协调器需要知道的信号，但不是要承担复杂动作的入口。

## 3. `doing.in` — 卡片进入 doing

**触发**：三条通路，行为必须一致

- 人类手动从 todo 拖到 doing（新卡）
- 人类从 done 拖回 doing（验证不通过）
- 协调器 auto-promote 从 todo 推到 doing

### 通用处理顺序

按这个顺序逐步处理，任意一步不通过就停下：

1. **看 label 是不是 `human-task`**。如果是——协调器 ignore，不启动 session、不创建 worktree、**不做 cap-check**。human-task 卡在 doing 是预期状态（人类直接处理），并发上限不约束它。
2. **过并发上限**（`acceptNewCard` 函数）。当前 doing 总数或该 project 计数超限——写"⏸ 并发上限已满"comment，把卡片移回 todo，结束这次处理。`needs-attention` 不加——人类拖卡循环重试是正常的 cap 兜底机制。
3. **建或复用 worktree**（如果这张卡需要）。没有 `no-worktree` label 时基于当前 main 创建 `card/<cardId>` 分支；目录还在就复用并 rebase。详见 `design.md §6.7`。
4. **跑 `worktree_init` 钩子**。失败只记 warning。
5. **启动 session**。写 `▶️ Started` comment、改 session title、发 prompt、调 `SessionManager.start_or_resume`。详见 `design.md §6.5`。

### 三条通路的差异

| 通路 | 谁移卡 | 差异 |
|---|---|---|
| 人类手动（todo→doing） | 人类 | Trello 已发 `doing.in`，协调器只响应 |
| 人类拖回（done→doing） | 人类 | 复用 worktree、读评论、调 `resume_session` |
| auto-promote | 协调器 | 先调 Trello 移卡，失败回滚计数 + 不启动 session |

三条通路在第 1 步之后走同一份处理顺序。

## 4. `doing.out` — 卡片离开 doing

**触发**：三种来源——人类从 doing 拖回 todo（暂停）；协调器从 doing 移到 todo（并发超限、session 失败、三件套超限）；协调器从 doing 移到 done（session 完成且三件套通过）。

### 移到 todo（暂停 / 失败）

**协调器动作**：

- abort session：调 `SessionManager.terminate`
- 清 in-memory 状态
- 保留 worktree 目录和 `card/<cardId>` 分支（不删，下次回来可复用）
- 写 comment（按原因）：人类主动中止 → "⏸ Paused by user"；session 异常 → "❌ Error in session <id>"；三件套超限 → 失败命令、摘要、重试次数；并发超限 → "⏸ 并发上限已满" + 原因（不加 `needs-attention`）

worktree 与 session 生命周期解耦——worktree 跨 session 保持，session 反复创建和销毁但 worktree 长期存活。

### 移到 done（完成）

**协调器动作**：

- 写"✅ Completed session <id>" comment
- 保留 session 元数据和 worktree（人类验证用）
- 写 Summary comment（`session.finish = "stop"` 时由 §5 总结流程处理）
- 无其它主动作——等人类验证

## 5. `session.finish` — session finish 信号

**触发**：协调器对每个 doing 卡片的 session 周期性探测（10s 间隔），调 `GET /session/{id}/message?limit=1`，判别 `info.finish` 字段值。

**核心判断**：`info.finish` 字段的 6 个可能值，**只有 5 个值触发完成流程**——`tool-calls` 不是完成信号。


| `info.finish` 值 | 协调器动作 |
|---|---|
| 字段缺失 | 跳过等下一轮 |
| `tool-calls` | **跳过等下一轮** |
| `stop` | 触发完成流程 + 完成后总结 |
| `length` | 异常完成：跳过总结 + 流程 + `needs-attention` |
| `content-filter` | 异常完成：跳过总结 + 流程 + `needs-attention` |
| `error` | 异常完成：跳过总结 + 流程 + `needs-attention` |
| `unknown` | 异常完成：跳过总结 + 流程 + `needs-attention` |

### `stop`（正常完成）

两阶段：

**阶段 1：完成后总结**（仅 `stop` 触发）

1. 向同 session 发固定中文 prompt（聚焦"本次运行的结果"）
2. 把 `sessionInfo.status` 切到 `statusSummarizing`，记录 `summary_started_at` 与 `lastFinish = "stop"`
3. 等下一轮 `info.finish`（最多 1 分钟超时）：提取 `type=text` 的 part 内容，`TrimSpace` 后取前 140 rune；超出末尾加 `…`；空字符串写"（本次会话未产生可读总结）"；写 `📝 Summary: <text>` comment

**阶段 2：完成流程**

1. 写"✅ Completed session <id>" comment
2. 若需要 worktree，确认 main 是否变化；变化则 rebase 后再验证
3. 跑三件套（build + lint + unittest）
4. **通过**：移动卡片到 done
5. **失败且未超重试上限**：对同 session 发修复 prompt（"三件套失败，错误如下：<log>。请修复并重试。"），卡片留在 doing；新轮 `info.finish` 出现后再次触发验证，循环 N 次
6. **失败且超限**：移动回 todo，写失败 comment，保留 worktree

**边界**：总结 prompt 发送失败 → 跳过总结阶段直接 done；总结 prompt 的 `info.finish` 异常 → comment 写"（总结生成失败: finish=<value>）"；等待期间 drag-out → drag-out 路径接管；等待超时（≥1 分钟）→ 跳过总结直接 done。

### 4 个异常 finish 值

**协调器动作**：

- 跳过后续总结阶段
- 写"❌ Error in session <id>" comment（带原因 + attach session 命令）
- 加 `needs-attention` label
- 跑三件套 + 移 done（同阶段 2）

异常 finish 表示"模型本轮不再说话"（`tool-calls` 除外），发总结 prompt 没有意义。`needs-attention` 是人类 attach session 看完整上下文的入口。

### `tool-calls` 或字段缺失

**协调器动作**：跳过等下一轮。

`tool-calls` 不是完成信号。模型调用工具后，等工具返回会继续生成下一轮 `assistant message`，那时会产生新的 `info.finish`。把 `tool-calls` 当作完成会过早停止协调器对 session 的监控。opencode 自己在 `prompt.ts:1341` 也把 `tool-calls` 判定为"未完成"。

## 事件源

- **Trello**：5 秒轮询 diff board snapshot → 4 个 `TrelloEvent`。
- **opencode**：finish watcher 每 10 秒探测 `info.finish` → `session.finish`。

两路经事件总线归一化为 `WorkflowEvent`，送入协调循环。详见 `design.md §6.3`。
