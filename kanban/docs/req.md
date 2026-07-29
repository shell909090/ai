# Trello Kanban Agent 需求文档

本文档描述系统要实现的用户可见行为。事件细节以 `docs/events.md` 为准；本文只保留产品目标、看板约定和边界规则。

## 1. 项目目标

本项目是 Trello 与 AI coding agent 之间的任务桥，用 Trello 看板控制 agent session：

- 人类用 Trello 卡片表达任务、排队、暂停和验收。
- 协调器根据 Trello 列表和 agent session 状态启动、终止、总结任务。
- agent 负责实际执行任务；Trello comments 负责记录关键过程。
- 系统支持多个任务并行，但必须受全局容量和项目容量限制。
- 人类始终可以通过拖卡或标签介入。
- 具体工程实践由项目自己的 `.kanban.yml` 定义；协调器不内置 worktree、构建、测试、部署或 PR 流程。

## 2. 看板与卡片

### 2.1 固定列表

系统至少使用这些 Trello list：

| list | 含义 |
|---|---|
| `todo` | 等待协调器启动的任务 |
| `doing` | 正在由 agent 执行或等待终止的任务 |
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
| `attention` | 需要人工关注。协调器在异常 finish、abort 超时、summary 超时、proj/agent 解析失败等情况下添加。 |
| `proj:*` | 指定任务归 AI 协调器处理，并声明所属项目，用于选择配置中的项目和项目容量计数。 |
| `agent:*` | 指定这张卡使用的 agent 配置名。必须匹配配置中的 `agents` key。 |
| 其他标签 | 协调器不解释，原样传给 agent driver；例如 `model:*` 可由 opencode driver 解释为模型选择。 |

看板由人类和 AI 共享；只有带 `proj:*` label 的卡片归 AI 协调器处理。
如果卡片没有 `proj:*` label，协调器忽略该卡片，不启动 agent session，不移动卡片，不占用容量。
如果 `proj:*` 解析失败，协调器把卡片移到 `done`，添加 `attention` label，并写 comment 说明原因。
如果卡片没有 `agent:*` label，使用 `kanban.default_agent`；如果存在多个 `agent:*` label、未知 `agent:*` label 或默认 agent 未配置，协调器把卡片移到 `done`，添加 `attention` label，并写 comment 说明原因。
`model:*`、`effort:*` 等非调度标签的含义由具体 agent driver 定义；协调器不得因这些标签不认识而拒绝启动任务。

## 4. 任务与容量

协调器在内存中维护 task 结构：

- card id
- session id
- proj
- agent
- abort time，可空
- summary time，可空

容量规则：

- 维护总 task 数和每个 proj 的 task 数。
- 启动前钩子运行期间的 pending task 已经占用容量，避免下一轮调度重复激活超过容量的任务。
- 容量只限制新任务启动，不作为 abort 已启动 session 的依据。
- 已启动 session 不会因为容量后来变满而被终止。
- 正常算法下，由协调器管理的 task 不应超过容量限制。

## 5. 调度循环

协调器周期性执行 timer 流程：

1. 检查所有 task 对应 session 状态。
2. 检查 Trello `doing` list 和 task 结构是否一致。
3. 检查 abort 和 summary 是否超时。
4. 如果容量未满，从 `todo` list 拉取可启动卡片，跳过没有 `proj:*` label 的卡片，按容量限制启动符合条件的卡片。

`docs/events.md` 是上述流程的精确规则来源。

## 6. session 状态行为

协调器通过 agent driver 读取 session 状态。driver 必须把底层工具的状态映射成三类：

| 状态 | 含义 |
|---|---|
| `running` | session 仍在执行，协调器跳过。 |
| `finished` | session 正常结束。 |
| `failed` | session 异常结束，需要人工关注。 |

例如 opencode driver 可把缺失 finish 和 `tool-calls` 映射为 `running`，把 `stop` 映射为 `finished`，把 `length`、`content-filter`、`error`、`unknown` 映射为 `failed`。

行为规则：

- `running`：session 仍在继续，跳过。
- task 已有 `abort`：说明用户已经把卡移出 `doing`，等待 abort 成功；session 终止后写 abort 成功 comment，并销毁 task。
- `failed`：把卡移到 `done`，添加 `attention`，写异常结束 comment，销毁 task。
- `finished` 且已有 `summary`：写完成 comment，把最后一条 summary message 写入 comment，同步运行完成钩子，把卡移到 `done`，销毁 task；完成钩子失败只添加 `attention` 和 comment，不阻止任务结束。
- `finished` 且没有 `summary`：向同一个 session 发送 summary prompt，并设置 task.summary 时间。

summary message 默认由 prompt 控制在 140 字以内，且 prompt 必须提示不要把敏感信息写入总结；协调器不限制“完成 comment + summary”组合后的总长度。
如果 summary 阶段产生异常状态，也添加 `attention`，因为人类应关注任何异常。

## 7. doing 检查

协调器周期性比较 task 结构和 Trello `doing` list：

- `doing` 里没有 `proj:*` label 的卡片忽略。
- 只在 task 结构里的卡片视为 `doing.out`。
- 只在 Trello `doing` list 里的卡片视为 `doing.in`。
- 必须先处理 `doing.out`，再处理 `doing.in`，避免容量计数错误。

## 8. doing.in

当一张带 `proj:*` label 的卡片进入 `doing` 且不在 task 结构中：

1. 解析 proj；无 `proj:*` 时忽略，解析失败则移到 `done` 并加 `attention`。
2. 解析 agent；无 `agent:*` 时使用默认 agent，解析失败则移到 `done` 并加 `attention`。
3. 检查总容量和该 proj 容量。
4. 容量超限：把卡移回 `todo`，写 comment 说明。
5. 容量允许：先建立 pending task 并占用容量，运行启动前钩子；钩子成功后使用解析后的 agent 和钩子返回的 workdir 建立 agent session。

## 9. doing.out

当 task 中的卡片不再位于 Trello `doing` list：

1. 向对应 agent session 发送 abort 信号。
2. 设置 `task.abort = now`。
3. 追加 comment 说明开始 abort。

abort 完成由后续 session 状态处理。abort 成功后运行 abort 钩子；abort 钩子失败只添加 `attention` 和 comment，不阻止 task 销毁和容量释放。
如果 abort 超时，协调器给卡片加 `attention`，写 abort 超时 comment，销毁 task 并释放容量计数。

## 10. 超时

- `now > task.abort + timeout`：abort 超时。添加 `attention`，写 comment，销毁 task，释放容量。
- `now > task.summary + timeout`：summary 超时。把卡移到 `done`，添加 `attention`，写 comment，销毁 task，释放容量。

## 11. 项目钩子与提示词

协调器只提供通用任务桥能力。每个项目可在仓库中提供 `.kanban.yml`，定义该项目如何把 Trello card 转换为 agent prompt，以及任务生命周期中的项目脚本。

`.kanban.yml` 至少支持：

- session 启动前钩子：在创建 agent session 前同步运行，可用于准备 worktree、安装依赖或检查环境。
- session 完成后钩子：在 summary 完成后同步运行，可用于 lint、unittest、修复检查或生成项目侧产物；失败只标记 `attention`，不阻止卡片进入 `done`。
- session abort 后钩子：在 abort 确认后同步运行，可用于清理临时目录或 worktree；失败只标记 `attention`。
- 全量 prompt 模版：深度定义 card 如何格式化为初始 prompt。
- prompt addon 模版：在默认或全量 prompt 后追加项目约束，用于简单补充要求，例如“开始前确认 git 干净”或“结束前运行 lint/unittest 并修复错误”。

启动前钩子可以把工作目录路径返回给协调器；协调器使用该路径创建 agent session。返回方式是写入协调器提供的专用结果通道，不依赖 stdout。是否使用 git worktree 完全由项目钩子决定，协调器不直接管理 worktree。

启动前钩子失败时，协调器不创建 agent session，把卡片移到 `done`，添加 `attention`，并写 comment 说明 hook 失败原因。

## 12. AI 看板操作

AI 不仅应能被 Trello 驱动，也应能按约定主动调整 Trello，减少人工维护 task 的成本。

系统应提供一个本地 Python 脚本和配套 skill，供 AI 执行常见看板操作：

- 新增 `todo` 卡片。
- 移动 card 到指定 list。
- 给 card 添加 comment。
- 给 card 添加或移除 label。
- 查询 list 和 card，便于 AI 在修改前确认当前看板状态。

Python 脚本不直接持有 Trello credential。脚本只把结构化操作请求提交给 kanban 协调器；协调器持有 Trello credential、校验请求并实际调用 Trello API。

一个 kanban 可以管理多个 proj。脚本新增 AI 任务时默认不要求用户手写 `proj:*` label，而是把当前工作目录传给协调器；协调器按路径级最长匹配推断 proj，并自动给新卡添加对应 `proj:*` label。匹配来源包括项目根目录和当前 task 管理的 workdir。只有当前目录不属于任何已配置项目或已知 workdir，或用户显式覆盖项目时，才需要额外指定 proj。

协调器必须为脚本提供本地控制 API。该 API 默认只监听本机地址，并使用独立 token 或本机权限控制；读写接口都必须鉴权，避免任意进程读取或修改 Trello。

配套 skill 应简洁说明何时使用脚本、如何先查询再修改、如何避免误操作，以及如何把批量拆分任务写入 `todo`。

## 13. 配置需求

配置至少需要包含：

- Trello board、list 和 label 名称。
- `kanban.default_agent`。
- `agents` 配置集合；每个 agent 配置必须包含 `type`，其他字段由对应 driver 解释。
- agent driver 所需地址、认证方式、默认模型和标签解释规则。
- 允许的 `proj:*` 映射。
- 全局 task 容量上限。
- 每个 proj 的 task 容量上限。
- timer 间隔。
- abort timeout。
- summary timeout。
- 每个项目的根目录或 `.kanban.yml` 路径。
- 项目钩子执行超时和输出长度限制。
- 本地控制 API 监听地址和认证 token 来源。

敏感信息不得写入 Trello comment、普通日志或示例配置。
