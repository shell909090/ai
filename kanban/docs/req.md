# Trello Kanban Agent 需求文档

本文档描述系统要实现的用户可见行为。事件细节以 `docs/events.md` 为准；本文只保留产品目标、看板约定和边界规则。

## 1. 项目目标

本项目用 Trello 看板控制 opencode session：

- 人类用 Trello 卡片表达任务、排队、暂停和验收。
- 协调器根据 Trello 列表和 opencode session 状态启动、终止、总结任务。
- opencode 负责实际执行任务；Trello comments 负责记录关键过程。
- 系统支持多个任务并行，但必须受全局容量和项目容量限制。
- 人类始终可以通过拖卡或标签介入。

## 2. 看板与卡片

### 2.1 固定列表

系统至少使用这些 Trello list：

| list | 含义 |
|---|---|
| `todo` | 等待协调器启动的任务 |
| `doing` | 正在由 opencode 执行或等待终止的任务 |
| `done` | 已完成、异常结束或需要人工关注的任务 |

其他 list 可由用户维护，但不参与本版自动调度。

### 2.2 卡片字段

卡片是任务载体：

- title：任务标题。
- description：任务说明。
- comments：协调器写入启动、终止、完成、异常和总结信息。
- labels：协调器读取控制标签。

## 3. 标签约定

| label | 行为 |
|---|---|
| `human` | 人工任务。协调器忽略，不启动 opencode session，不占用容量。 |
| `attention` | 需要人工关注。协调器在异常 finish、abort 超时、summary 超时、proj/model 解析失败等情况下添加。 |
| `proj:*` | 指定任务所属项目，用于选择配置中的项目和项目容量计数。 |
| `model:*` | 指定这张卡使用的模型。必须匹配配置中的模型 allowlist。 |

如果卡片没有 `proj:*` label，使用配置中的默认项目。
如果 `proj:*` 解析失败，协调器把卡片移到 `done`，添加 `attention` label，并写 comment 说明原因。
如果卡片没有 `model:*` label，使用配置中的默认模型；如果 `model:*` 解析失败，同样移到 `done` 并添加 `attention`。

## 4. 任务与容量

协调器在内存中维护 task 结构：

- card id
- session id
- proj
- abort time，可空
- summary time，可空

容量规则：

- 维护总 task 数和每个 proj 的 task 数。
- 容量只限制新任务启动，不作为 abort 已启动 session 的依据。
- 已启动 session 不会因为容量后来变满而被终止。
- 正常算法下，由协调器管理的 task 不应超过容量限制。

## 5. 调度循环

协调器周期性执行 timer 流程：

1. 检查所有 task 对应 session 是否产生 `session.finish`。
2. 检查 Trello `doing` list 和 task 结构是否一致。
3. 检查 abort 和 summary 是否超时。
4. 如果容量未满，从 `todo` list 拉取可启动卡片，跳过 `human` 卡片，按容量限制启动符合条件的卡片。

`docs/events.md` 是上述流程的精确规则来源。

## 6. session.finish 行为

协调器通过 opencode 接口读取 session 最后一条消息：

```text
GET /session/:session_id/message?limit=1
```

最后一条消息的 `info.finish` 有 6 个合法值：

- `stop`
- `tool-calls`
- `length`
- `content-filter`
- `error`
- `unknown`

行为规则：

- 没有 `info.finish`：session 仍在继续，跳过。
- `tool-calls`：session 仍在工具调用流程中，跳过。
- task 已有 `abort`：说明用户已经把卡移出 `doing`，等待 abort 成功；finish 后写 abort 成功 comment，并销毁 task。
- 非 `stop`：把卡移到 `done`，添加 `attention`，写异常结束 comment，销毁 task。
- `stop` 且已有 `summary`：写完成 comment，把最后一条 summary message 写入 comment，把卡移到 `done`，销毁 task。
- `stop` 且没有 `summary`：向同一个 session 发送 summary prompt，并设置 task.summary 时间。

summary message 默认由 prompt 控制在 140 字以内，但协调器不限制“完成 comment + summary”组合后的总长度。
如果 summary 阶段产生异常 finish，也添加 `attention`，因为人类应关注任何异常。

## 7. doing 检查

协调器周期性比较 task 结构和 Trello `doing` list：

- `doing` 里带 `human` label 的卡片忽略。
- 只在 task 结构里的卡片视为 `doing.out`。
- 只在 Trello `doing` list 里的卡片视为 `doing.in`。
- 必须先处理 `doing.out`，再处理 `doing.in`，避免容量计数错误。

## 8. doing.in

当一张非 `human` 卡片进入 `doing` 且不在 task 结构中：

1. 解析 proj；无 `proj:*` 时使用默认 proj，解析失败则移到 `done` 并加 `attention`。
2. 解析 model；无 `model:*` 时使用默认模型，解析失败则移到 `done` 并加 `attention`。
3. 检查总容量和该 proj 容量。
4. 容量超限：把卡移回 `todo`，写 comment 说明。
5. 容量允许：使用解析后的 model 建立 opencode session，建立 task，容量计数加一。

## 9. doing.out

当 task 中的卡片不再位于 Trello `doing` list：

1. 向对应 opencode session 发送 abort 信号。
2. 设置 `task.abort = now`。
3. 追加 comment 说明开始 abort。

abort 完成由后续 `session.finish` 处理。如果 abort 超时，协调器给卡片加 `attention`，写 abort 超时 comment，销毁 task 并释放容量计数。

## 10. 超时

- `now > task.abort + timeout`：abort 超时。添加 `attention`，写 comment，销毁 task，释放容量。
- `now > task.summary + timeout`：summary 超时。把卡移到 `done`，添加 `attention`，写 comment，销毁 task，释放容量。

## 11. 配置需求

配置至少需要包含：

- Trello board、list 和 label 名称。
- opencode server 地址和认证方式。
- 默认模型。
- 允许的 `model:*` 映射。
- 默认 proj。
- 允许的 `proj:*` 映射。
- 全局 task 容量上限。
- 每个 proj 的 task 容量上限。
- timer 间隔。
- abort timeout。
- summary timeout。

敏感信息不得写入 Trello comment、普通日志或示例配置。
