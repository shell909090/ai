# Trello Kanban Agent 工作流 — 需求文档

> 本文档定义一个由 Trello 看板驱动的多 AI agent 协同工作流系统。覆盖目标、实体、行为、约束与角色职责。
>
> 本文档只描述"要什么"：产品行为约束、协调动作约定、协调约束、权限边界。实现细节、API 路径、源码引用、配置格式、算法选择等"怎么做"的内容见 `docs/design.md`。

---

## 1. 项目目标

构建一个工作流系统，使用 Trello 看板作为人与 AI agent 之间的协作界面。人类通过拖动卡片管理任务队列，AI agent 在被分派时自动执行任务。系统应满足：

- **可解释性**：人类能随时理解 agent 当前在做什么、历史做过什么、为什么做。
- **可控性**：人类保留最终决策权，可随时暂停、否决、重新分派任务。
- **可扩展性**：支持多卡片并行执行，支持任务在多个执行周期间持久化。
- **不替代人类**：AI 负责执行和初步判断完成，人工负责验证和归档。
- **代码工作可隔离**：多卡片并发改代码时互不干扰。

### 1.1 核心思想：协调（Orchestration）

本系统的核心是**协调**——Trello 看板是协调界面，opencode session 是协调对象，协调器是协调者。

**双向事件驱动的闭环**：

- 人类（或自动机制）把卡片拖到某个 list → 卡片 list 归属变化 → 协调器感知 list 变化 → 协调器触发对应的协调动作（创建 / 暂停 / 恢复 / 验证 / 合并）
- opencode session 的 `info.finish` 等事件反馈给协调器 → 协调器把卡片移到对应的 list（done / todo / 留 doing 等）

**5 个关键事件**驱动整个协调循环：

- **Trello 端 4 个事件**：卡片在两个关键 list（`todo` / `doing`）上的入和出——`todo.in` / `todo.out` / `doing.in` / `doing.out`
- **opencode 端 1 个事件**：`session.finish`（session 最后一条 message 的 `info.finish` 字段存在）

其他 list 归属变化（`icebox.*` / `done.*` / `archived.*`）**不参与自动协调**——done 等待人类验证、archived 由人类触发合并、icebox 是候选入口。

**list 归属是协调信号**：

- 卡片在 `todo` → 协调器按调度策略把它推到 `doing`（启动 session）
- 卡片在 `doing` → 协调器监控对应 session 的状态，等待完成信号
- 卡片在 `done` → 协调器等待人类验证，验证后由人类决定是否合并（`archived`）
- 卡片在 `archived` → 协调器触发合并队列处理

**list 本身不是状态机的状态变量**——它是协调流程的**信号源**。所谓"卡片从 todo 移到 doing"不是一次"状态转移"，而是协调器对一次"信号"（list 归属变化）做出的协调动作（启动 session）。协调器不维护状态机的"合法转移"规则；它只问"卡片在 list X，协调器应该做什么"。因此本章不使用"状态机 / 状态转移"语言，统一用"协调动作 / 协调约束"描述。

**外部引用**：5 个关键事件的响应逻辑、与 `CoordinationSignal` 的关系、双向事件驱动的协调循环机制见 `docs/design.md §6.3` / `§6.4`。

---

## 2. 核心实体

### 2.1 看板 (Board)

唯一一块工作看板，包含五个固定列（见第 3 节）。项目内所有任务在此看板上流转。

### 2.2 卡片 (Card)

任务的最小单位。卡片是工作流的核心对象，承载任务的所有信息：

- **标题**：任务的简短描述。
- **描述 (description)**：AI 干活儿的源头。最终被 AI 视为任务说明书。
- **评论 (comments)**：双向沟通通道。AI 记录执行事件、人类补充信息、双方提问与答复。
- **附件 (attachments)**：过程记录的归档载体，主要存放 markdown 文件。
- **状态**：由卡片所在列决定（见第 3 节）。
- **worktree 引用**（见第 6 节）：涉及代码改动时，卡片与一个 git worktree 1:1 绑定。

### 2.3 评论 (Comment)

- **AI 视角**：记录执行事件（启动、暂停、错误、完成）的数据载体。
- **人类视角**：理解过程、补充信息、回答 AI 提问的渠道。
- 评论按时间顺序追加，不可删除（除人为清理外）。

### 2.4 附件 (Attachment)

存放过程记录，主要为 markdown 文件。附件用于**备查**，不作为 AI 执行任务的依据。AI 执行时依据的是卡片描述，而非附件。

### 2.5 Agent 会话 (Session)

AI 执行任务的一次完整对话上下文。卡片与 session 是一对多关系（同一张卡片可能经历多个 session）。session 生命周期：

- **启动**：卡片从 todo 进入 doing 时创建。
- **执行中**：agent 调用工具完成任务。
- **结束**：session 进入 idle（agent 自报完成 / 等用户输入 / 异常）。
- **暂停**：卡片被拖回 todo，session 被强制终止。
- **下一轮**：卡片再次进入 doing 时，**新开** session，第一轮 prompt 注入历史。
- **与 worktree 的关系**：session 终止不影响 worktree；worktree 跨 session 保持，绑定到 card 而非 session。

### 2.6 Worktree

代码改动的隔离工作环境。每个涉及代码改动的卡片拥有一个 worktree（见第 6 节）。worktree 与 session 解耦：session 反复创建和销毁，worktree 长期存活。

---

## 3. 看板列定义

Trello 看板上的五个 list 是**协调流程的信号**，不是状态机的状态变量。卡片在 list 之间的移动，是协调器收到信号后**对协调动作的承担**——例如"人类把卡片拖到 doing"不是一次状态转移，而是协调器收到"该卡片应被分派"的信号。

按协调流程从左到右排列：

| 列名 | 协调含义 | 谁在此列操作 |
|---|---|---|
| **icebox** | 候选任务：AI 生成、人类未审稿 | AI（创建）/ 人类（审稿后拖到 todo） |
| **todo** | 排队：已批准、等待分派 | 协调器（按调度策略推到 doing） / 人类（手动拖到 doing） |
| **doing** | 执行中：对应 opencode session 正在跑 | 协调器（监控 session）/ AI（执行并改卡片）/ 人类（拖回 todo 中止） |
| **done** | 待验证：AI 自行判断完成、等待人类验证 | 人类（验证后归档或拖回 doing） |
| **archived** | 已结案：人类验证完成 | 协调器（触发合并队列） / 人类（拖入此列） |

### 3.1 协调动作与触发方

协调器对每种 list 归属变化触发对应的协调动作。下表是"信号 → 协调动作"的映射：

| 信号（list 归属变化） | 协调动作 | 触发方 |
|---|---|---|
| (新卡进入) icebox | 创建 icebox 卡（苏格拉底后） | AI |
| icebox → todo | 审稿通过，进入排队 | 人类 |
| todo → doing | 启动 opencode session：建 worktree、跑钩子、改 session title、发 prompt | 协调器（auto-promote 或人类手动） |
| doing → done | session 结束且三件套通过，把卡片移到 done | 协调器 |
| doing → todo | 暂停或失败：清 in-memory 状态 / abort session / 保留 worktree | 协调器（并发超限、session 失败、三件套超限） / 人类（主动中止） |
| done → doing | 验证不通过，附评论拖回；协调器读评论、复用 worktree、继续 session | 人类 |
| done → archived | 验证通过：触发合并队列（no-worktree 直接完结） | 人类 |
| archived → (合并完成) | 合并成功：删 worktree、分支保留 4 周；合并失败：建 human-task 卡插入队列 | 协调器 |

> 注：以上是协调器对"list 变化信号"承担的动作；不是合法转移表。约束部分会在 §11.1 不可越权中以协调约束的形式表达。

### 3.2 协调约束

下列约束是协调层面的硬性边界——任何角色违反都会被协调器拒绝 / 修正：

- **AI 不可把卡片直接移入 archived**：archived 必须是人类验证后的产物；这是协调器认为"任务已结案"的前提。
- **AI 不可把卡片移回 icebox**：icebox 是新候选的入口，不是回退目标。
- **任何角色不可跨级移动**：如 todo → done（绕过执行）、icebox → doing（绕过审稿）。协调器发现后会自动修正。
- **任何角色不可在 worktree 未通过验证前宣称 done**：done 列的进入必须由协调器主导（基于三件套 + finish 信号），不允许人类或 AI 直接拖。
- **human-task 卡不可触发 AI session**：见 §6.6.4，是协调器对"卡片进入 doing"信号的特殊排除。

---

## 4. 卡片生成阶段（icebox）

### 4.1 流程

1. 人类在普通 opencode 会话中与 AI 对话，提出大方向。
2. AI 通过苏格拉底式提问澄清需求细节。
3. 对话结束前，人类嘱咐 AI：把任务拆解并添加到 trello。
4. AI 调用 trello MCP 工具，将拆解后的任务作为新卡片放入 icebox。
5. 卡片描述由 AI 整理，**不包含对话过程**。
6. 苏格拉底过程与拆解细节写入 markdown 附件（备查）。

### 4.2 卡片描述规范

描述必须是**结构化的任务说明书**，AI 后续执行时直接照做。包含但不限于：

- 任务目标
- 验收标准
- 涉及的文件 / 模块
- 依赖关系（与其他卡片的关系）
- 实现约束（如果有）

### 4.3 附件规范

苏格拉底过程记录、需求拆解的中间过程，作为 markdown 文件上传为附件。附件**不**作为执行依据，仅备查。附件仅在卡片创建时生成一次，不在每次执行时重新生成。

---

## 5. 卡片执行阶段（doing）

### 5.1 Session 启动

触发条件：卡片从 todo 进入 doing。

- 协调器在 Trello 上检测到该转移。
- 判断此卡片是否有未完结历史（通过扫描卡片评论，识别之前 session 启动 / 结束的 comment）。
- 如有代码改动需求，创建或复用 worktree（见第 6 节）。
- 创建新 session（不复用旧 session）。
- 协调器写一条启动 comment：`▶️ Started session <id>`，包含本次任务目标摘要与初始 todo（如有）。
- 调用 opencode 启动新 session，第一轮 prompt **无需人工构造**。

### 5.2 Session 执行

agent 在 session 中：

- 通过 todowrite 工具规划子任务。
- 通过 trello MCP 工具读取 / 修改卡片。
- 实时通过评论记录关键事件。
- 可以编辑卡片描述（如任务范围在执行中发生变化）。
- 在其专属 worktree 中进行代码修改（见第 6 节）。

**session 与卡片是 1:N 关系**，**worktree 与卡片是 1:1 关系**。同一卡片被多次拖入 doing 时，每次都新开 session 但复用同一个 worktree。

### 5.3 第一轮 Prompt 不需协调器构造

第一轮 prompt 由 opencode session 自己从环境上下文组装。协调器**不**预先拼装 prompt。

### 5.4 Session 结束 / 暂停

#### 5.4.1 正常完成（session finish + 验证）

**核心约定**：完成检测完全由协调器主动探测实现——**agent 不主动调用任何端点声明结束**，无 done URL、无 token、无提示词注入。

**原理**：opencode session 最后一条 message 暴露 `info.finish` 字段，标识模型本轮是否已结束说话。协调器**根据字段值分流**——不是所有字段值都触发完成流程。模型 emit `finish` 本身就是 agent 的"完成信号"——无需再让 agent 多调一次 HTTP，也无需 MCP 桥接 / webfetch。

**`finish` 字段含义与协调器处理**：

| 值 | 含义 | 协调器处理 |
|---|---|---|
| 字段缺失 | 模型仍在流式生成，或只有 user prompt 没有 assistant 回复 | watcher 跳过 |
| `tool-calls` | 模型本轮调用了工具，等工具返回后会继续 | **跳过，等下一轮**（不是完成信号） |
| `stop` | 模型本轮正常结束 | 触发完成流程 + 完成后总结（5.4.4） |
| `length` | 上下文长度上限 | 异常 finish：跳过总结，直接完成 + 加 `needs-attention` |
| `content-filter` | provider 内容过滤拒绝输出 | 异常 finish：跳过总结，直接完成 + 加 `needs-attention` |
| `error` | 模型本轮出错 | 异常 finish：跳过总结，直接完成 + 加 `needs-attention` |
| `unknown` | 未识别的 finish 值 | 异常 finish：跳过总结，直接完成 + 加 `needs-attention` |

**关键决策**：

- **`tool-calls` 不是完成信号**。模型调用工具后，等工具返回会继续生成下一轮 `assistant message`，那时会产生新的 `info.finish`。把 `tool-calls` 当作完成会过早停止协调器对 session 的监控。opencode 自己在 `packages/opencode/src/session/prompt.ts:1341` 也把 `tool-calls` 判定为"未完成"。
- 只有 `stop` 是"模型真的说完了"信号。其他 4 个值（`length` / `content-filter` / `error` / `unknown`）是异常结束，模型本轮不会再说话。向异常结束的模型发总结 prompt 是浪费 token 且不会得到有用信息，所以异常 finish 全部跳过后续总结，直接完成 + needs-attention。

**为何不依赖 agent 主动信号**：让 agent 主动调 webfetch / HTTP endpoint 是重复劳动——也带来 token 校验、一次性消费、并发锁、post-done cool-down 等一整套复杂度。`info.finish` 字段检测本身即是 agent 的"完成信号"，无需引入额外机制。

**流程**：

- 协调器后台 finish watcher 周期性探测每个 doing 卡片的 session（实现细节见 `docs/design.md §6.5`）。
- 判别 `info.finish` 字段值：
  - **字段缺失**（流式生成中）：跳过，等下一轮。
  - **`tool-calls`**（模型调用工具，等工具返回）：跳过，等下一轮——模型还会继续，不是完成信号。
  - **`stop`**：触发完成流程。先走完成后总结（5.4.4），拿到 summary 后再走 1-4。
  - **4 个异常值**（`length` / `content-filter` / `error` / `unknown`）：跳过后续总结，直接走 1-4 + 加 `needs-attention`。
  1. 写 `✅ Completed session <id>` comment。
  2. 若需要 worktree，确认 main 是否变化；变化则 rebase 后再验证。
  3. 协调器跑三件套（build + lint + unittest）：
     - **通过**：卡片移到 done。
     - **失败**：协调器对**同一个 session** 发修复 prompt：`三件套失败，错误如下：<log>。请修复并重试。`
       - agent 看到自己之前的代码 + 失败原因
       - agent 继续工作，新一轮 `info.finish` 触发 watcher 再次验证
       - 超过重试上限 → 协调器拖回 todo，写 comment
  4. 若 `info.finish ∈ {length, content-filter, error, unknown}`：除上述流程外，加 `needs-attention` label + 写错误 comment（`❌ Error in session <id>`），提示人类 attach session 调查。
- **session 持续存在**直到：
  - 卡片 archived（合并成功后清理）
  - 卡片永久回 todo
  - session 异常终止
- **完成后总结（详见 5.4.4）**：仅当首个 finish 是 `stop` 时触发。其他 finish 值都不发总结。

**外部引用**：opencode `info.finish` 字段的完整枚举与归一化逻辑在 opencode 源码 `packages/llm/src/schema/ids.ts` 与 `packages/opencode/src/session/llm/ai-sdk.ts`（详见 `docs/design.md §6.5`）。

#### 5.4.2 暂停（卡片被拖回 todo）

- 协调器检测到卡片回到 todo。
- 写一条暂停 comment：`⏸ Paused by user`。
- 写一条 session 结束 comment（含 session 终止时的 todo 状态）。
- worktree 与分支保留，供下次 resume 复用。
- **session 也保留**（不删除），下次进入 doing 时可继续。

#### 5.4.3 失败 / 异常

**A. session 异常**（LLM API 错误、网络问题、agent 主动 abort 等）：

- 协调器把卡片拖回 todo。
- 写错误 comment：`❌ Error in session <id>`，含错误信息。
- worktree 保留。
- session 终止。

**B. session 在异常 finish 上结束**（`info.finish` 异常值，详见 5.4.1）：

- 协调器 finish watcher 检测到异常 finish。
- 写 `✅ Completed session <id>` comment + 异常 finish 错误 comment。
- 加 `needs-attention` label（详见 5.5）。
- 跑三件套 + 走完成流程（同 5.4.1）。
- 等人类 attach session 调查。

#### 5.4.4 完成后总结（summary on stop）

session 本轮 `info.finish = "stop"`（模型正常结束）后、卡片移 done 之前，协调器向**同一个 session** 发一个总结 prompt，要求模型用 140 个字以内简要描述本次工作。协调器等模型下一轮 `info.finish` 出现后，从最后一条 message 的文本部分提取文本，作为一条独立 comment 写入 Trello。

**作用域**：仅当首个 finish 是 `stop` 时触发。异常 finish 都跳过本节流程，直接完成 + 加 `needs-attention`，不发总结 prompt。

目的：人类做 done 验证时，能在 Trello 上一眼看到 agent 自述的工作内容，不必 attach 到 opencode。

**完成流程**（调整后）：

1. finish watcher 检测到 `info.finish = "stop"` 出现。
2. **不**立即写 `✅ Completed`；改为向同 session 发总结 prompt（固定中文，详见 5.4.5）。
3. 等下一轮 `info.finish`：
   - 拉取 session 最后一条 message
   - 提取文本内容，取前 140 个字（超出末尾加 `…`）
   - 若结果为空，comment 文案为 `（本次会话未产生可读总结）`
   - 写一条 `📝 Summary: <text>` comment
4. 继续 5.4.1 原流程：`✅ Completed session <id>` comment、异常 finish 处理、移 done。

**失败与边界**（行为约定）：

- 总结 prompt 发送失败：跳过总结步骤，按 5.4.1 原流程直接 done。
- 总结 prompt 的 `info.finish` 异常：comment 写 `（总结生成失败: finish=<value>）`，仍走原流程 done，**不**额外打 `needs-attention`（已完成任务，失败提示仅作信息）。
- 等待期间卡片被拖出 doing：drag-out 处理仍按原逻辑清掉 in-memory 状态并 abort session；总结 prompt 视为失效。
- 等待超时：若总结 prompt 发出后超过 1 分钟仍未出现下一轮 `info.finish`，跳过总结、按 5.4.1 原流程直接 done。

**核心原则**：

- 复用同一个 session 发总结 prompt，不开新 session（省 token、保上下文）。
- 总结是软指标：发不出去 / 模型不答 / 模型答得不好，都不应阻塞卡片完成。
- 140 字上限是面向人类阅读的硬性要求，模型写超 140 字会被截断（加 `…`），不重试。

**总结内容要求**：

总结 prompt 的目标不是"重新描述任务本身"——任务说明在卡片描述里已存在。总结的语义必须是"本次运行的*结果*"：偏重于"做了什么"、"产生了什么成果"、"修改/创建/查看了哪些文件、跑过什么命令、得到什么输出"，而非"要做什么"。具体措辞在 scheduler 端固定（详见 5.4.5）。

**外部引用**：实现细节（API 调用、文本提取算法、超时阈值、失败码）见 `docs/design.md §7.7`。

#### 5.4.5 完成后总结 prompt 文案与 session 标识

scheduler 发给 opencode 的总结 prompt 是固定中文文案，由协调器侧控制（不在卡片描述里，避免 agent 改写）。同时为了便于人类在 Trello 上一眼定位 session，scheduler 在所有写 session id 的 comment 里都把 id 渲染成可点击链接。

**固定 prompt 文案**（scheduler 拼好后发出去，不依赖卡片描述）：

```
请用 140 个字以内简要总结本次运行的*结果*，不是任务说明。聚焦：
- 实际做了哪些操作（执行了哪些命令、修改/创建/查看了哪些文件）
- 关键产出（新增/修改/删除的文件、跑通的测试、产生的数据、得到的结论）
- 任何值得人类关注的副产品（意外发现、未完成项、需要 follow-up 的事）

仅输出总结本身，不要任何前缀、解释、Markdown 标记。
```

**session id 的链接渲染**：

所有写 session id 的 comment（▶️ Started / ✅ Completed / ❌ Error）默认把 id 渲染成 markdown 链接，URL 模式：

```
<OpenCodeBaseURL>/<base64url(WorkDir)>/session/<sessionID>
```

`base64url` 编码规则与 opencode web 自身一致（**这是项目对 opencode 外部行为的引用**，编码规则与源码位置见 `docs/design.md §6.4.1`）。

scheduler 已有 `OpenCodeBaseURL` 与 `WorkDir`，无需新加配置；人类在 Trello 上一键直达 opencode web 的对应会话。

若 `OpenCodeBaseURL` 配的是 `http://127.0.0.1:4096` 而 opencode web 实际经 reverse proxy 暴露在 `http://opencode.home:1234/`，需要把 `OpenCodeBaseURL` 改成可被浏览器访问的 base（这点与 API 调用 base 共享同一配置；如有冲突，等未来多 binding 阶段再考虑拆分）。

**session 重命名为卡片标题**：

scheduler 在 todo→doing 创建 opencode session 之后、发 prompt 之前，把 session 的 `title` 设为卡片 title，让 opencode web 列表与 Trello 列表一一对应。rename 失败不影响主流程。

### 5.5 needs-attention 机制

session 在 `info.finish` 异常值上结束（详见 5.4.1），协调器标记 `needs-attention`（"agent 异常退出 / 上下文耗尽，需人类调查"）。

**标记方式**：
- **Label**：`needs-attention`
- **Comment**：`❌ Error in session <id>`（异常 finish 的原因 + attach 命令）

**人类处理路径**：

- **接 session 看上下文**：用 opencode 提供的 attach 命令查看 session，决策是否继续
- **人类决定 abort**：手动把卡片拖回 todo
- **人类决定改描述重做**：拖回 todo，编辑描述

**label 自动清除时机**：

- 卡片离开 doing 列（archived 或回 todo）
- session 被终止

**核心原则**：

- `info.finish` 异常值视为"agent 异常退出"信号，统一打 `needs-attention`
- 简单、单源触发（一个字段值），不依赖 agent 主动行为
- 人类 attach session 后可看到完整上下文，自己判断怎么处理
- kanban 不是 AI 与人类对话的唯一渠道

---

## 6. Worktree 与代码合并

卡片涉及代码改动时，必须有独立的 git worktree。本节定义 worktree 生命周期、合并策略、验证三件套与冲突处理。

### 6.1 基本规则

- 每个涉及代码改动的卡片拥有**唯一**的 worktree 和分支，跨 session 保持不变。
- 路径：`<repo>/.worktrees/<cardId>`
- 分支名：`card/<cardId>`
- session ID 仅出现在 comment 中，**不影响** worktree 标识。
- 即便卡片被多次拖入 doing（经历多个 session），worktree 始终是同一个。
- 纯文档/非代码类卡片可不需要 worktree，但建议保持一致以简化心智。
- 卡片是否需要 worktree 通过 Trello **label** 标记（见 6.8）。

### 6.2 生命周期

| 卡片状态变化 | worktree 操作 |
|---|---|
| todo → doing（有 `no-worktree` label） | **跳过** worktree 创建（无代码改动） |
| todo → doing（无 label） | **创建** worktree 和分支（基于当前 main HEAD） |
| doing → todo（人工暂停） | **保留**（分支+目录都在） |
| doing → doing（同卡再次进入） | **复用**现有 worktree；分支 rebase 到当前 main |
| doing → done（agent 自报完成） | **保留**（等人类验证） |
| done → archived（有 `no-worktree` label） | **跳过** 合并操作 |
| done → archived（无 label） | **合并**分支到 main，**删除** worktree 目录，分支保留 4 周 |
| done → doing（人类验证不通过） | **保留**（agent 继续基于现有分支工作） |
| doing → todo（session 失败） | **保留**（分支+目录都在） |

### 6.3 分支基线

- worktree 分支 `card/<cardId>` 基于 main **创建时刻的 HEAD** 切出。
- 卡片在 todo 队列中等待时，其他已 archived 卡片可能已合入 main。
- 当此卡片最终进入 doing 时，**必须先 rebase 当前 main**，再开始工作。
- 卡片在 done 前若发现 main 已变，**再次 rebase** 并重新跑验证三件套。

### 6.4 验证三件套

所有项目**强制**要求配置 linter 和 unittest。验证三件套：

1. **build**：项目能成功构建
2. **lint**：linter 全部通过
3. **unittest**：所有单元测试通过

#### 6.4.1 验证命令定义

- 项目根目录的 `AGENTS.md` 或专门的 `.trello-verify` 文件中定义验证命令。
- 形式如 `make verify`、`npm run check && npm test`。
- 协调器读取并执行。
- **项目要求配置 linter 和 unittest，未定义的项目合并后果自负**。

**外部引用**：验证命令的 `.trello-verify` 文件格式、字段定义、加载方式见 `docs/design.md §6.7`。

#### 6.4.2 worktree 钩子（环境初始化）

worktree 创建后、agent session 启动前，协调器调用项目声明的钩子做环境初始化。

- 钩子在 worktree 目录中执行（`cd <worktree_path> && <hook_command>`）。
- cardId 在路径里，项目脚本通过 `pwd` 或 `basename $(pwd)` 即可获得，**不需要**协调器注入环境变量。
- 钩子成功（exit 0）：继续 session 启动。
- 钩子失败（exit 非 0）或未配置：session 启动前什么都不做，agent 在主目录（fallback 行为）。
- 依赖安装、Docker 拉起、数据初始化等都由项目脚本自己处理。

**外部引用**：钩子的 `.trello-verify` 字段定义与声明方式见 `docs/design.md §6.7`。

#### 6.4.3 验证时机

| 触发点 | 验证者 | 失败后果 |
|---|---|---|
| finish watcher 检测到 `info.finish` 字段存在 | **协调器** | 对同 session 发修复 prompt |
| 修复 prompt 后 watcher 再次检测到新 finish | 协调器 | 同上，循环 N 次 |
| 超过重试上限 | 协调器 | 拖回 todo，写 comment |

**核心原则**：验证由协调器主导，不依赖 agent 自报。`info.finish` 是触发信号，三件套是质量门。

### 6.5 合并队列

- 多张卡片 archived 时，orchestrator 按归档时间顺序处理。
- **串行合并**：一次只处理一张卡。
- 当前卡合并失败 → 创建"解决冲突"卡 → 插入队列头部。
- 后续卡片必须等待"解决冲突"卡完成才能合并。

### 6.6 合并与冲突处理

#### 6.6.1 触发条件

- 卡片 A 已合入 main。
- 卡片 B archived 后，协调器尝试合并 B 到 main 时 git 报冲突。

#### 6.6.2 冲突的解

冲突只有两种合理选择：
- **merge**：合并双方
- **discard**：放弃一边

AI 只能尝试 merge。如果 AI 解决不了（验证失败），**创建 human-task 卡**（见 6.6.4）。

#### 6.6.3 AI 自动 merge 流程

- 在冲突卡**自己的 worktree** 里解决（不用临时 worktree）。
- AI 调工具解决冲突。
- 跑三件套。
- 验证通过 → 合并提交到 main → 走合并流程。
- 验证不通过 → 创建 human-task 卡片。

#### 6.6.4 human-task 卡片

协调器自动创建新卡片并直接放入 todo 列：

- **Label**：`human-task`
- **标题**：解决 [cardA] 与 [cardB] 在 main 的合并冲突
- **描述必须包含**：
  - 冲突的文件、行号、原始冲突内容
  - 涉及的两条分支及其当前状态
  - main 当前 HEAD
  - AI 自动 merge 尝试及失败原因
  - 验证失败的具体输出
  - 验收标准：通过 build + lint + unittest
- **卡片行为**：
  - 进入 doing：协调器**不**建 AI session，**不**创建 worktree
  - 人类在主仓库直接处理（merge、revert、改冲突）
  - 完成后人类自己改卡片状态
- 此卡片**阻塞**所有后续 archived 卡片的合并。

#### 6.6.5 集成测试失败处理

集成测试失败也是 human-task 卡的场景：

- 协调器**不**自动回滚已合并的 worktree
- 人类决定是否 git revert
- 创建 human-task 卡：修复 [原卡A] 导致的集成问题
  - 描述：失败命令、输出、相关 commit
  - 走与冲突卡相同的 human-task 流程

#### 6.6.6 meta-card 统一

冲突卡和集成测试失败卡都是 **human-task meta-card**，结构与流程相同：

| 触发场景 | 描述来源 |
|---|---|
| merge 冲突 AI 解决不了 | 冲突文件 + AI 失败原因 |
| 集成测试失败 | 失败命令 + 输出 + 相关 commit |

不再区分"解决冲突卡"和"修复集成卡"两类。

### 6.7 worktree 清理

- archived 成功合并到 main 后，**立即删除** worktree 目录。
- 分支 `card/<cardId>` **保留 4 周**后由 orchestrator 清理（git worktree prune + branch delete）。
- 保留分支用于回滚和审计。
- archived 的卡不会 resume，worktree 删后无影响。

### 6.8 无 worktree 卡片

部分卡片不涉及代码改动或不适合使用 worktree，通过 Trello **label** 标记。

#### 6.8.1 适用场景

- 纯文档、流程配置（修改 `AGENTS.md`、CI 配置等元文件）
- 基础设施调整（修改 `docker-compose.yml`、`Makefile` 等）
- 集成测试相关卡片（见 6.9）
- 跨多 worktree 的元工作（重命名、批量重构调度等）

#### 6.8.2 label 约定

- label 名：`no-worktree`（kebab-case 严格匹配）
- 项目 `AGENTS.md` 中需写明本项目使用的全部约定 label
- orchestrator 启动 session 前读取卡片 labels，匹配 `no-worktree` 则跳过 worktree 创建/合并/清理

#### 6.8.3 行为差异

- 卡片进入 doing：不创建 worktree，agent 在主仓库目录工作
- 卡片 archived：orchestrator 跳过合并操作，直接进入归档完成态
- 卡片自验和 orchestrator 兜底验证仍执行（针对主仓库当前状态）
- 暂停 / 恢复：不涉及 worktree 操作

### 6.9 集成测试

集成测试与 unittest 是两类不同性质的测试，**协调器完全不管集成测试**。

#### 6.9.1 测试分层

| 类型 | 范围 | 依赖 | 触发方 |
|---|---|---|---|
| **unittest** | 单元 / 模块级 | 无外部依赖 | 协调器跑（worktree 内） |
| **integration test** | 系统级 | 需外部环境（DB、redis、网络服务） | 人工 / CI |

#### 6.9.2 label 约定

- label 名：`needs-integration-test`
- 标记的卡片在 done → archived 时人类必须先跑集成测试
- 卡片描述应写明集成测试步骤（环境准备、命令、预期结果）

#### 6.9.3 人类验证流程

done 列的卡片若带 `needs-integration-test` label：

- 人类验证必须包含集成测试
- 集成测试通过 → 拖到 archived，触发 worktree 合并
- 集成测试失败 → 写 comment 说明问题，拖回 doing
- 集成测试失败且已合并 → 走 6.6.5 创建 human-task 卡

#### 6.9.4 label 体系总览

| Label | 触发方 | 行为 |
|---|---|---|
| 无 label | 协调器 | 走常规 ai-task 流程 |
| `ai-task`（可选） | 协调器 | 显式标记 AI 任务 |
| `human-task` | 协调器 | 不建 session，不创建 worktree |
| `no-worktree` | 协调器 | 跳过 worktree 创建/合并/清理 |
| `needs-integration-test` | 人类 | archived 前必须跑集成测试 |
| `needs-attention` | 协调器 | session 异常 finish（`error` / `length` 等），需人类 attach session 调查 |

---

## 7. 卡片验证与归档（done / archived）

### 7.1 协调器验证通过 → done

- finish watcher 检测到 session 最后一条 message 的 `info.finish` 字段存在（见 5.4.1）。
- 协调器跑三件套（见 6.4.3）。
- **验证通过**：协调器将卡片移到 done。
- **验证失败**：协调器对同 session 发修复 prompt，agent 继续（不进入 done）。
- 完成摘要写在 done 前的 comment 中。

### 7.2 人类评审方法

卡片进入 done 后、人类决定批准前，需要手段审查改动。本节定义评审的工程要求。

#### 7.2.1 Diff 审查（代码层面）

人类直接进入 worktree 查看 diff：

- worktree 路径：`<repo>/.worktrees/<cardId>`（见 6.1）
- 查看命令：`cd <worktree-path> && git diff main`
- 不需要 orchestrator 生成附件或评论

#### 7.2.2 worktree 启动（产品层面）

需要看产品界面（web、CLI、API 等）时，worktree 必须可启动运行。

**worktree 路径**

- 路径：`<repo>/.worktrees/<cardId>`（见 6.1）
- 人类在 host 上可直接 `cd` 进入

**Dev server**

- 项目自管：agent 启动 dev server，自己知道端口
- agent 通过 trello MCP 的 comment 工具报告 URL：`🌐 Dev URL: http://localhost:<port>`（与完成信号独立——完成由协调器检测 `info.finish` 字段，Dev URL 是 agent 自报的运行入口）
- 协调器**不**做端口分配
- 多 worktree 并行时端口冲突由项目自己处理

**评审体验**

- 人类点击 Trello 卡片 comment 中的 Dev URL
- 浏览器打开，看到当前 worktree 的产品形态

#### 7.2.3 数据层与外部依赖（项目级责任）

**核心原则**：scheduler 不解决数据层和外部依赖问题，只提供**钩子**。项目自管自己的运行环境。

**scheduler 提供的钩子**

| 钩子 | 触发时机 | 用途 |
|---|---|---|
| `pre_dev_start` | worktree 创建后，dev server 启动前 | 准备数据环境（拉起 docker、复制数据、跑迁移等） |

钩子在 `.trello-verify` 中声明。**外部引用**：钩子的 `.trello-verify` 字段定义见 `docs/design.md §6.7`。

**scheduler 调用钩子时**：在 worktree 目录中执行（`cd <worktree_path> && <hook_command>`）。**cardId 在路径里**，项目脚本通过 `pwd` 或 `basename $(pwd)` 即可获得，不需要 scheduler 注入环境变量。

**钩子成功的路径**（理想情况）

- 钩子脚本完成：docker compose up、复制主数据库数据（脱敏）、跑迁移
- 钩子执行成功（exit 0）→ scheduler 启动 dev server
- 人类通过 Dev URL 看到产品界面

**钩子失败 / 未配置的路径**（fallback）

- scheduler **不做 fail-closed**，也不中止
- 直接启动 dev server，让它**连主数据库**
- 起码还有个指望——万一 schema 没变呢？总比不知道好不好的 docker 强
- 如果主 DB 也不兼容：人类盲点通过/拒绝，与"项目没做脚本"是同一情况

**三种项目状态下的行为**

| 项目状态 | scheduler 行为 | 评审体验 |
|---|---|---|
| 钩子存在 + 成功 | dev server 跑在 worktree 的专属环境 | 看到产品界面 |
| 钩子存在 + 失败 | dev server 启动，连主 DB | 可能能用（schema 兼容） / 可能崩（不兼容） |
| 没钩子 | dev server 启动，连主 DB | 同上 |

**关键认知**

- scheduler 只编排**流程**（worktree、session、合并、冲突）
- 环境准备（DB、redis、外部服务）是**项目代码**的一部分
- 项目在 `AGENTS.md` 或 README 中写明 dev 环境启动方式
- 钩子是 scheduler 给项目的"介入点"，**不是必填项**
- 钩子失败 = 没钩子，行为一致

#### 7.2.4 评审检查清单

人类评审 done 卡片时的标准动作：

1. **cd 到 worktree 看 diff**（7.2.1）— 代码变更是否符合预期
2. **访问 Dev URL**（7.2.2）— 产品功能是否正常（前提：项目提供了一键拉起脚本）
3. **查看 unittest 结果**（6.4.3）— orchestrator 已验过
4. **集成测试**（如带 label）— 人类按描述命令执行
5. **遗留检查** — 无调试代码 / TODO / 临时文件
6. **决策**（见 7.3）— 批准 / 否决

**如果 Dev URL 不可用**（项目没做钩子脚本 + 主 DB 不兼容）：

- 退化为基于 diff + unittest 的盲点评审
- 在卡片 comment 中标注"无产品界面评审"
- 决策需明确承担风险

### 7.3 人类验证

人类在 done 列审阅卡片（评审方法见 7.2）后做出决策：

- **卡片带 `needs-integration-test` label**：必须先跑集成测试（见 6.9.4），通过后再拖到 archived。
- **卡片带 `no-worktree` label**：拖到 archived 即可，orchestrator 跳过 worktree 合并。
- **普通卡片**：拖到 archived，触发 worktree 合并（见第 6 节）。
- **不通过**：在卡片评论中说明问题（必填），将卡片拖回 doing。

### 7.4 拖回 doing 时的要求

人类拖回 doing 时**必须**附带评论，说明：

- 验证发现的问题
- 对 agent 的具体要求
- 任何补充上下文

agent 再次进入该卡片时，从评论中读取这些要求，并在现有 worktree 分支上继续工作。

---

## 8. 评论规范

评论是**双向沟通通道**，不是单向事件流。必须同时支持：

1. **AI 写入执行事件**（结构化、机器可读）
   - `▶️ Started session <id>`
   - `✅ Completed session <id>`
   - `⏸ Paused by user`
   - `❌ Error in session <id>`
   - `📝 Summary: <text>`（完成后总结，详见 5.4.4）
2. **人类补充信息**（自由文本）
   - 验证不通过的原因
   - 范围变更说明
   - 业务背景
   - 对 agent 的具体要求
3. **双方对话**（问答形式）
   - 人类向 agent 提问（agent 在后续 session 中回应）
   - agent 向人类提问（人类在评论中回答）

人类**有权**也**应当**在评论中补充信息。AI 看到的人类评论与 AI 自己写的 comment 享有同等地位。

**comment 模板与字段**：固定前缀、AI/协调器事件 comment 格式见 `docs/design.md §8`。

---

## 9. 并发与调度

### 9.1 并行执行

多个卡片同时处于 doing 状态时，**每个卡片对应一个独立的 opencode session，并行执行**。每个 session 拥有独立的 worktree，互不干扰。

### 9.2 并发上限

系统必须设置 doing 列卡片数量的并发上限（具体值在实现时确定，建议初始为 3）。超出上限的卡片行为：

- 协调器将其从 doing 拖回 todo。
- 写入 comment 说明并发限制原因。
- 卡片保持 todo 状态等待下次机会。
- worktree 创建/合并/清理开销也影响上限选择。

### 9.3 协调器职责

协调器（独立进程）负责：

- 监听 Trello 看板变化。
- 维护 doing 列卡片的并发数量。
- 触发 session 启动（卡片进入 doing）。
- 触发 session 终止（卡片回到 todo / 异常）。
- 写生命周期 comment。
- 处理失败回退。
- **管理 worktree 生命周期**（创建、合并、清理）。
- **运行验证三件套**。
- **处理合并冲突**。
- 不参与 prompt 构造、不调用 opencode 之外的 LLM（自动解决冲突除外，见 6.6.2）。

---

## 10. 失败处理

本节处理 session 级别的失败（合并相关失败见 6.6）。

### 10.1 定义

以下情况视为失败：

- **session 异常**：LLM API 错误、网络问题、agent 主动 abort
- **session 异常 finish**：`info.finish` 异常值（上下文耗尽、provider 拒绝、模型出错等，详见 5.4.1）
- **三件套反复失败**：超过重试上限（3 次，建议值）后 agent 仍修不好
- **needs-attention 长期无人工**：label 加上后长时间无人干预

### 10.2 处理

- session 异常：拖回 todo，写 `❌ Error` comment
- 三件套超限：拖回 todo，写 comment 说明失败原因
- 失败卡片回到 todo 队列，人类可重试、修改描述、或抛弃
- worktree 保留
- **不**引入 "blocked" 列
- **不**允许失败卡片停留在 doing

---

## 11. 角色与权限

| 角色 | 协调职责 |
|---|---|
| **人类** | 触发苏格拉底对话；批准 / 修改 / 抛弃 icebox 卡片；将卡片从 todo 拖到 doing；从 done 验证后归档或拖回 doing；处理 human-task 卡；处理 needs-attention；attach session 调查；处理合并冲突；提供初始方向 |
| **AI agent (苏格拉底阶段)** | 在普通会话中与人类对话；拆解任务；调用 trello 工具创建 icebox 卡片 |
| **AI agent (执行阶段)** | 在 doing 卡片对应的 session 中执行任务；调其他工具改卡片；agent **不**主动声明完成——由协调器通过 `info.finish` 字段被动检测 |
| **协调器（协调器）** | 监听 Trello；按 list 归属触发协调动作；建/终止 session；管理 worktree；写生命周期 comment；跑三件套；处理并发与失败；处理合并；标记 needs-attention；将失败卡片回 todo |

### 11.1 协调层面的不可越权

- **AI 不可把卡片移入 archived**：archived 必须是人类验证后的产物；协调器不接受 AI 的 archived 信号。
- **AI 不可把卡片从 done 移走**：done 列的进出只能由人类（验证后归档 / 拖回重做）或协调器（验证失败后回 doing）承担。
- **协调器不可把卡片从 done 移走**：done 移走只允许人类（验证后回 doing 或 archived）。
- **AI 不自行移卡片到 done**：done 进入必须由协调器主导（基于三件套 + finish 信号），不允许人类或 AI 直接拖。
- **human-task 卡不可触发 AI session**：见 §6.6.4，是协调器对"卡片进入 doing"信号的特殊排除。
- **AI 不主动声明完成**：完成由协调器通过 `info.finish` 字段被动检测；agent 不调任何"我完成了"的端点。

这些约束是协调器接受 list 信号时的硬性边界——违反会被协调器拒绝或自动修正。

### 11.2 Card-driven 配置的安全边界

卡片可在 label 声明 `proj:X`（路径） / `model:X`（model）。协调器必须按以下规则处理：

- 无 label：使用 binding 默认（`repo.main_path` / `opencode.default_model`）
- 单 label 命中 allowlist（`repo.allowed_paths` / `opencode.allowed_models`）：用该值
- 单 label 不在 allowlist：**FAIL**（不静默回退）
- 同类型多 label（多 `proj:*` 或多 `model:*`）：**FAIL**
- FAIL 动作：写 comment 到卡说明（具体 label 值 + 冲突原因）+ 加 `needs-attention` label + **不启动 session**。卡留在 doing 等人修。

**核心原则**：

- 协调器**绝不**从 card description / comment 文本里读路径或 model——只有 `labels[]` 字段是配置源。
- 路径 / model 字符串启动时验证：路径必须可解析且 `os.Stat` 存在；model 必须是 `<providerID>/<modelID>` 形式（`/` 分隔，无路径分隔符）。
- 即使 allowlist 命中，路径再过清理与 `..` 检测——防 allowlist 配置被改坏。

**外部引用**：allowlist 字段定义、fail-fast 行为的具体实现路径校验算法见 `docs/design.md §6.4` 与 §9。

---

## 12. 验收标准

项目完成需满足：

1. 人类可在 Trello 上完成 icebox → todo → doing → done → archived 完整流转。
2. 卡片 todo→doing→todo（暂停）→doing（恢复）循环中，agent 能从评论历史重建上下文。
3. 多个 doing 卡片可并行执行，并发数量受控，每个有 worktree 的卡有独立 worktree。
4. **finish watcher 检测到 session `info.finish` 字段存在后，协调器主导跑三件套；通过则移 done；失败则发修复 prompt 给同 session**。
5. session 持续存在，可多轮 `info.finish` 触发验证循环。
6. archived 后 worktree 自动合并到 main，合并冲突时 AI 尝试 merge，失败则创建 `human-task` 卡。
7. `human-task` 卡由人类在主仓库直接处理，协调器不建 AI session、不创建 worktree。
8. session 异常 finish → 加 `needs-attention` label + comment，人类 attach session 调查。
9. 评论同时承载 AI 事件日志与人类补充信息，agent 后续 session 能同时读到。
10. 苏格拉底过程以 markdown 附件形式归档（仅创建时一次），卡片描述不含过程噪音。
11. 人类可从 done 拖回 doing，agent 再次进入时能读到反馈意见。
12. AI 不可直接归档卡片；归档必须由人类操作。
13. 协调器为独立进程，不依赖 opencode 自身实现 Trello 事件循环。
14. agent **不**主动声明完成；协调器通过 `info.finish` 字段被动检测 session 结束，无需 MCP 桥接 / webfetch / done URL / token / 提示词注入。
15. 项目要求配置 linter 和 unittest 验证命令；未定义的项目合并后果自负。
16. worktree 与卡片 1:1 绑定，跨 session 复用；archived 合并成功后 worktree 立即删除，分支保留 4 周。
17. 合并队列串行执行，当前卡失败时创建 `human-task` 卡插入队列头部。
18. 卡片可通过 `no-worktree` label 跳过 worktree 创建/合并/清理。
19. 卡片可通过 `needs-integration-test` label 标记需人类在 done → archived 前跑集成测试。
20. worktree 创建后协调器调用项目声明的 `worktree_init` 钩子做环境初始化（可选，失败 fallback）。
21. 集成测试失败不触发协调器自动回滚；人类选择是否 revert，并创建 `human-task` 修复卡。
22. 卡片可通过 `proj:X` / `model:X` label 声明路径与 model；不在 allowlist 或多 label → FAIL + needs-attention，不启动 session。

---

## 13. 开放问题

实现阶段需要确认的架构级问题：

1. **并发上限的具体数值**（建议初始为 3，可配置）
2. **三件套失败重试上限**（建议初始为 3）
3. **finish watcher 轮询间隔**（建议 10s，可配置）
4. **附件 markdown 命名规范**（建议：`<card-id>-<stage>.md`）
5. **worktree 分支保留时长**（建议 4 周后清理）
6. **`worktree_init` 钩子超时**（建议 10 分钟）
7. **协调器与 opencode server 的部署关系**（同机 / 跨机 / 容器化）
8. **多用户远程访问 worktree**（单用户本地 `cd`；多用户需 orchestrator 暴露 Web 终端）
9. **session 在卡片 archived 后的保留策略**（立即删 / 保留 N 天 / 永久保留供审计）
