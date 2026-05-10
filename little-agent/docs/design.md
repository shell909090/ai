# 设计文档

## 1. 概述

### 1.1 目标与前提

最小可运行 Agent 系统：对话 + tools。

- 内核 `asyncio`。
- 与 ACP 等效语义，同进程内不机械复制 JSON-RPC 包装。
- 长期存在三个 frontend：`cli`、`web`、`acp`。
- tool 通过配置文件注册，描述对齐 MCP。
- 对话历史采用倒排链；运行时优先使用对象引用。

### 1.2 模块划分

一级模块四个：

1. `agent`：维护会话、分支、倒排链、取消、冻结、fork、压缩；调用 backend 与 tools。
2. `tools`：tool 注册、筛选、调用；统一接入内置 tool 与 MCP tool provider。
3. `frontends`：用户交互。
4. `backends`：模型供应商接入。

`session`、`chain`、`persistence` 是 `agent` 内部实现，不作为一级模块暴露。

启动脚本 `little-agent` 完成装配（YAML 配置加载、logger 初始化、依赖拼装、启动 client），通过 `pyproject.toml` 的 `[project.scripts]` 注册，是装配层而非一级模块。

### 1.3 模块边界与依赖方向

```text
little-agent (script)
  -> frontends
  -> agent
  -> tools
  -> backends

frontends -> agent
agent -> tools
agent -> backends
```

约束：

1. `agent` 不直接依赖具体 frontend / backend / tool 实现。
2. 启动脚本负责把具体实现注入到协议接口上。
3. `frontends <-> agent` 用 ACP 类接口（详见 §4），稳定边界是 `Client`。
4. `tools <-> agent` 用 MCP 类接口（详见 §3），稳定边界是 `ToolRegistry`。
5. `backends <-> agent` 走项目内部接口（详见 §5）。

## 2. Agent

### 2.1 倒排链节点

```python
@dataclass(slots=True)
class Node:
    id: str
    prev: "Node | None"
    created_at: datetime


@dataclass(slots=True)
class UserPromptNode(Node):
    kind: ClassVar[str] = "user_prompt"
    prompt: str | list[ContentBlock]


@dataclass(slots=True)
class AssistantResponseNode(Node):
    kind: ClassVar[str] = "assistant_response"
    text: str
    frozen: bool = False


@dataclass(slots=True)
class ToolCallNode(Node):
    kind: ClassVar[str] = "tool_call"
    calls: dict[str, dict[str, Any]]   # call_id -> {tool_name, arguments}


@dataclass(slots=True)
class ToolResultNode(Node):
    kind: ClassVar[str] = "tool_result"
    results: dict[str, dict[str, Any]]  # call_id -> {status, content}
    frozen: bool = False


@dataclass(slots=True)
class SummaryNode(Node):
    kind: ClassVar[str] = "summary"
    summary: JSONValue
```

规则：

1. 运行时通过 `prev` 对象引用回溯。`id` 主要用于 save/load、日志、调试和 fork 入口。
2. 节点整体逻辑 append-only。
3. `frozen` 字段只出现在写入过程中可变的节点类型上：`AssistantResponseNode` 与 `ToolResultNode`。`UserPromptNode`、`ToolCallNode`、`SummaryNode` 创建即不可变，无需 `frozen`。
4. 可变节点在任意时刻只能被一个 session 作为活跃尾节点持有。
5. 触发冻结的时机（由 session 负责管理）：
   - session 追加新节点时，旧尾若为可变类型，立刻冻结。
   - session 被 fork（失去唯一引用）时，当前尾若为可变类型，立刻冻结。
   - 当前 turn 结束或被取消时，尾节点立刻冻结。

### 2.2 Session 状态

`Session` 本身就是状态对象，不再额外定义 `SessionState` 或 `ActiveTurn` 结构。

最小状态至少包括：

1. `id`
2. `cwd`
3. `tail`（当前链尾）
4. 当前是否存在活跃 turn
5. 当前 turn 是否已请求取消
6. pending prompt 队列（容量默认 3，满则抛 `SessionBusy`）

多 session 并发规则：

1. 非 fork 产生的独立 session 各自持有完全独立的链条。
2. fork 产生的新 session 在 fork 点之前共享已冻结的历史节点，fork 点之后各自追加新节点，互不干扰。
3. 任何时刻，同一个可变节点只能被一个 session 作为活跃尾节点持有。

### 2.3 Tool Call 与 Tool Result 节点约束

一次模型返回的一组并行 tool calls 落为一个 `ToolCallNode`，其后紧接一个 `ToolResultNode` 承载这组调用的结果。

`ToolCallNode.calls` 结构：

```python
{
    "call_xxx": {
        "tool_name": str,
        "arguments": dict[str, Any],
    },
}
```

`ToolResultNode.results` 结构：

```python
{
    "call_xxx": {
        "status": "completed" | "failed" | "cancelled",
        "content": JSONValue,
    },
}
```

规则：

1. `ToolCallNode` 由 backend 一次写入后立刻冻结，生命周期内不可变。
2. `ToolResultNode` 跟随其后创建，按 `call_id` 逐步回填，直到全部结果就位或 turn 结束。
3. 结果与状态更新依靠 `call_id` 对应，不依靠顺序。
4. tool 执行抛出的 `ToolInvokeError` / `ToolExecutionError` 在编排层被捕获，写入对应 `call_id` 的结果中（`status = "failed"`，`content` 为异常信息）。**异常绝不冒出 prompt turn**，模型拿到失败反馈后自主决定下一步。
5. 若执行中被取消，`ToolResultNode` 中尚未完成的 call 标记为 `cancelled`，节点立刻冻结。
6. 节点冻结之后到达的迟到结果直接丢弃。

### 2.4 fork 规则

1. `session.fork()` 基于当前 session 状态创建一个新 session。
2. 新旧 session 共享已有历史节点。
3. fork 前如果当前尾节点仍可变，必须先冻结，再进行浅拷贝式分叉。
4. fork 时如果当前 session 存在活跃 turn，直接抛异常。
5. `fork()` 不暴露 `from_node_id` 参数。如未来需要"从指定历史节点分叉"，再以新扩展方法加入。

### 2.5 编排流程

`Session.prompt()` 流程：

1. 若当前 session 已有活跃 turn：进入 pending 队列；队列满则抛 `SessionBusy`。否则立刻占据，标记"有活跃 turn"。
2. 在当前尾部追加 `UserPromptNode`，旧尾若为可变类型先冻结。
3. 进入主循环（循环上限 `MAX_TURN_ITERATIONS`，默认 20）：
   1. 调用 `session.get_turn_tool_map()` 得到本轮可见 tool 子集（`allowed_tools` 为 None 时返回全部已注册 tool）。调用 `Backend.generate(session)` 得到 async iterator；backend 内部读取 `session.get_turn_tool_map()` 而非 `session.agent.tools.list()`。遍历产出：
      - 遇到 `SessionUpdate`（`agent_message_chunk` / `thinking_chunk`）：立即通过 `client.update()` 转发给 frontend。
      - 遇到 `BackendTurnResult`：保存为 `result`，退出遍历循环。
      - 若 backend 抛 context-overflow 错误：进入 §2.6.4 in-turn retry 路径。
   2. `result.finish_reason == "completed"`：追加 `AssistantResponseNode`（冻结），跳出主循环，返回 `("end_turn", output_text)`。
   3. `finish_reason == "tool_call"`：
      - 追加 `ToolCallNode`（冻结），通过 `Client.update(session, tool_call)` 通知 frontend。
      - 追加 `ToolResultNode`（可变）。
      - 调用前检查每个 tool name 是否在本轮允许列表内；不在列表的 call 直接记录失败（`status="failed"`，`content="Tool not in allowed list"`），不实际调用。
      - 并发执行允许的 tools（`asyncio.gather`），结果按 §2.3 写入。
      - 每个结果就位通过 `Client.update(session, tool_call_update)` 通知 frontend。
      - 全部结果到位或 turn 被取消后，`ToolResultNode` 冻结。
      - 进入下一次循环。
   4. `finish_reason == "cancelled"`：跳出循环，返回 `("cancelled", partial_output)`。
4. 超过 `MAX_TURN_ITERATIONS`：抛异常。
5. 过程中任意时刻收到 cancel：
   - 若正在等待 backend 返回：等当前调用自然结束，不再进入下一轮循环。
   - 若正在并发执行 tools：`asyncio.gather` 解除 wait，已完成的结果正常写入，未完成的 call 在 `ToolResultNode.results` 中标记 `cancelled`，节点立刻冻结；后到的结果因节点已冻结而被丢弃。
   - 最后冻结任何未封口节点，返回 `("cancelled", partial_output)`。
6. 真正失败（backend 异常、链条不一致等）直接抛异常，不返回 `failed`。
7. 无论成功、取消还是异常，finally 阶段先按 §2.6.2 判据评估是否触发 post-turn 自动压缩：
   - 触发：保持活跃 turn 标记不释放，异步调度 compress 任务（`asyncio.create_task`），由该任务在结束时释放标记；pending 队列在 compress 结束后才唤醒。
   - 未触发：立即清理活跃 turn 标记；pending 队列非空时唤醒下一个排队协程。
8. `Session.cancel()` 只影响当前活跃 turn（含 post-turn compress 任务），不清空 pending 队列。

`Session.cancel()` 规则：

1. 若 session 没有活跃 turn，直接返回。
2. 若有活跃 turn，只设置"已请求取消"标记。
3. 真正的停止、冻结与收尾由 `prompt()` 所在协程完成。

### 2.6 压缩

#### 2.6.1 Compressor 协议

```python
class Compressor(Protocol):
    async def compress(self, head: Node) -> Node: ...
```

规则：

1. 输入：要压缩的链头节点（含通过 `prev` 可达的全部历史）。
2. 输出：新的链头节点（通常是 `SummaryNode`，但协议不强制）。
3. `Compressor` 由启动脚本按配置构造，并在 `Agent.__init__` 注入。
4. 若配置中存在名为 `compressor` 的 backend，则 compressor 使用它；否则与 agent 共用同一 backend。
5. `Session.compress()`：
   - agent 未注入 compressor：抛异常。
   - 活跃 turn 存在：抛异常。
   - 否则调用 `compressor.compress(tail)`，把返回节点设为 session 新的 tail。
6. 旧链保留，用于回放与 fork。不修改旧链，不从旧链摘节点。
7. agent 编排在每次 turn 结束后自动评估并按需调度 `compress()`，触发策略详见 §2.6.2。

#### 2.6.2 自动触发策略

post-turn 触发：每次 `Session.prompt()` 即将返回前（成功、取消、异常都参与判定）评估判据。命中则 agent 异步调度 compress 任务（`asyncio.create_task`），prompt() 立即返回 `(stop_reason, output)` 给 frontend。

compress 任务运行期间复用 session 的活跃 turn 标记（与正常 turn 互斥）。新到达的 prompt 通过既有 pending 队列等待；compress 结束后释放标记，pending 唤醒。

判据（满足任一条件即调度）：

1. **token 阈值（首选）**：本 turn 最后一次 backend 调用的 `usage.input_tokens + usage.output_tokens` 与该 backend 的 `context_window` 相比，比值大于 `R`。`R` 由 agent 配置项 `R` 调整，默认 `0.5`，取值范围 (0, 1]。
2. **字符兜底**：本 turn 没有有效 usage 数据（usage 为 None 或字段为 0），从 tail 往前累加每个节点序列化后的字符数，除以 4 得到 token 估算值，同样比较 `R` 阈值。
3. **context-overflow 兜底**：见 §2.6.4 in-turn retry 路径，turn 内同步触发。

#### 2.6.3 算法

保留窗口：最近 `K` 个 turn 不参与压缩。`K` 由 compressor 配置项 `keep_turns` 调整，默认 `5`，下限 `3`（配置低于 3 时报警并强制使用 3）。

turn 边界：从一条 `UserPromptNode` 起，到下一条 `UserPromptNode` 之前的所有节点（含 ToolCallNode / ToolResultNode / AssistantResponseNode）属于同一个 turn。

压缩算法：

1. **压缩区上界**：从 tail 往前回溯，找到最后一条 `SummaryNode` 即为上界（再往前皆为已压缩内容）；若链上无 SummaryNode，上界为链首。
2. **保留区**：tail 起最近 `K` 个 turn 的所有节点。
3. **被压区**：上界与保留区之间的所有节点，按 turn 切分。
4. **压缩**：每个被压 turn 一次 LLM 调用，压成一条 `SummaryNode`，保留关键事实、决策和上下文（"相对详细"，非极致压缩）。多个被压 turn 通过 `asyncio.gather` 并发发起调用，实际并发由 backend 层的 `max_concurrency` 限制；按时序串接结果。任一并发请求失败按 §2.6.4 处理（all-or-nothing：丢弃整批，旧链保留）。
5. **新链拼装**：上界之前的旧 SummaryNode + 本次新产出的 SummaryNode + 保留区。

历史上限 `W = compressed_window * context_window`（tokens）。`compressed_window` 是 compressor 配置项，单位为比例（取值范围 (0, 1)），默认 `0.2`；`context_window` 取自 primary backend 配置。

历史上限处理：

1. SummaryNode 没有 usage 数据，统一用字符数 / 4 估算。
2. 时机：压缩算法拼装新链后立刻执行。
3. 算法：从最新 SummaryNode 往旧累加估算 token；累加值首次超过 `W` 时，该位置之前的所有 SummaryNode 整体丢弃，与 SummaryNode 边界对齐，不切断单条 SummaryNode。

#### 2.6.4 失败处理

`Compressor.compress()` 抛出异常（含 context-overflow、超时、其他 backend 异常）时：

1. **post-turn 路径**：异常向 frontend 抛，frontend 显示错误；session 链结构不破坏。处理方式与普通 backend 调用失败一致。
2. **in-turn overflow retry 路径**：在主循环中 backend 抛 context-overflow 时，agent 同步调用 `compressor.compress(self.tail)` 一次，把返回值赋给 `self.tail`，然后对当前 backend 调用 retry 一次。retry 仍 overflow 则按普通 backend 异常向上抛，turn 终止。该路径不通知 frontend。

#### 2.6.5 日志

每次自动压缩输出 INFO 级别日志，至少包含：

- 触发判据：`token_threshold` / `char_fallback` / `overflow_retry`
- 触发值：估算 token 数与对应 `context_window`
- 被压 turn 数与新生成 SummaryNode 数
- 历史上限触发的丢弃 SummaryNode 数（若有）
- 压缩耗时（毫秒）

### 2.7 Permissions

权限系统采用 **Chain of Responsibility** 模式。

#### 2.7.1 PermissionChecker 接口

```python
class PermissionChecker(Protocol):
    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool: ...
```

`Client` 接口包含完全相同的方法签名，天然满足 `PermissionChecker`，作为 chain 末端（向用户询问）。

#### 2.7.2 Chain 构建

`Agent.permissions: PermissionChecker` 始终存在（非 Optional）。未配置时默认值为 `client`，即所有 tool 调用直接询问用户。

chain 从配置 list 尾部往头部构建，请求从头部向尾部流转，第一个能决策的 checker 截断 chain：

```
checker[0] → checker[1] → ... → client
```

list 为空 → 全部流转到 `client`，每次询问用户。

#### 2.7.3 内置 Checker 类型

**YesManChecker**：无配置项，始终返回 True。用于"放行一切未被前面 checker 拦截的请求"，或测试场景。

**BlackWhiteListChecker**：

```yaml
- type: blackwhitelist
  blacklist:
    - "dangerous_*"
  whitelist:
    - "read_*"
```

- `blacklist`：fnmatch 模式列表；tool name 匹配任意一条 → 立即 deny（返回 False），截断 chain。
- `whitelist`：fnmatch 模式列表；tool name 匹配任意一条 → 立即 allow（返回 True），截断 chain。
- black 优先于 white。
- 两者均不匹配 → 传递给 `next`。

未来可扩展：`BashRiskChecker`（解析 bash 参数识别高危模式）、`RegexChecker` 等，接口一致。

#### 2.7.4 ToolInvoker 中的调用

每个 tool call 只做一次调用：

```python
allowed = await session.agent.permissions.request_permission(
    session, tc.tool_name, {"arguments": tc.arguments}
)
```

返回 False → `ToolResultNode.results[call_id] = {status: "failed", content: "Permission denied"}`，不执行。`allowed_names`（turn 级别工具可用性）作为独立前置检查，不经过 permission chain。

### 2.8 Memory

记忆系统为可选注入子系统：

```python
class Memory:
    async def recall(self) -> str | None: ...
    async def remember(self, session: Session) -> None: ...
```

规则：

1. 由启动脚本按配置构造，在 `Agent.__init__` 注入。
2. 注入时每轮 `_run_turn` 开始前调用 `recall()`：返回的文本作为 `SummaryNode` 注入到 session tail。
3. 每轮 `_run_turn` 结束后（无论成功、取消、异常）调用 `remember(session)` 更新记忆。
4. 未注入：跳过 recall 与 remember。

## 3. MCP 协议与 Tools

agent 不关心 tool 来源（内置 Python 实现、配置加载的插件、未来的 MCP provider），统一为一组 MCP 类能力：列出工具、调用工具。

### 3.1 共享类型

```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from little_agent.types import JSONValue

AsyncToolFn = Callable[[dict[str, JSONValue]], Awaitable[JSONValue]]


@dataclass
class ToolArgDef:
    name: str            # 参数名，传给 LLM 和 JSON Schema
    type: str            # JSON Schema 类型，如 "string"、"object"、"integer"
    desc: str            # 参数描述，传给 LLM
    required: bool = False


@dataclass
class ToolDef:
    desc: str                                              # 工具描述
    args: list[ToolArgDef] = field(default_factory=list)   # 参数列表


ToolMap = dict[str, ToolDef]                               # key 是 tool name
```

约束：

1. `ToolDef` 不含 name（name 是 `ToolMap` 的 key）；不含 callable（callable 在 `ToolManager` 内部存储）。
2. `ToolMap` 是纯描述结构，只传给 backend / LLM，不含 callable。
3. `ToolArgDef` 自动转换成最小 MCP `inputSchema`：顶层固定为 `type: "object"`，字段填入 `properties`，`required` 列表由 `required=True` 的字段推导。
4. 当前只支持顶层 object + 一层平铺标量字段；不支持嵌套对象、数组、枚举、默认值（详见 §6.3）。
5. tool 输入与输出都必须可 JSON 序列化。
6. `session_id`、`cwd`、`call_id` 不进入 tool 函数签名；由 agent 内部管理。

### 3.2 ToolProvider 接口

```python
from collections.abc import Iterator

class ToolProvider(Protocol):
    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]: ...
```

规则：

1. `__iter__` 逐个 yield `(name, tooldef, fn)` 三元组。
2. `fn` 签名固定为 `async (args: dict[str, JSONValue]) -> JSONValue`；参数整体作为一个 dict 传入，不使用 `**kwargs`。
3. 同步 tool 由 provider 自行用 `asyncio.to_thread` 包装成 async 后再 yield。
4. provider 不负责路由；路由由 `ToolManager` 负责。

### 3.3 ToolRegistry 协议

```python
class ToolRegistry(Protocol):
    def register(self, provider: ToolProvider) -> None: ...
    def desc_tool(
        self,
        names: set[str] | None = None,
        *,
        exclude: set[str] | None = None,
    ) -> ToolMap: ...
    def __getitem__(self, name: str) -> AsyncToolFn: ...
```

规则：

1. `register(provider)` 迭代 provider，将 `(name, tooldef, fn)` 注册到 registry；name 冲突时 raise `ValueError`。
2. `desc_tool(None)` 返回全部已注册工具的 `ToolMap`。
3. `desc_tool(set())` 返回空 `ToolMap`（"默认全部"与"指定空集"语义分离）。
4. `desc_tool({name, ...})` 只返回指定名称的工具描述，未注册的名称忽略。
5. `exclude` 可选，指定后从结果中删除对应名称：`result = (全集 if names is None else names) − (exclude or ∅)`。
6. `__getitem__(name)` 返回对应工具的 `AsyncToolFn`；name 不存在时 raise `KeyError`。调用方直接 `await registry[name](args)` 执行工具。
7. 执行失败通过异常表示，由 agent 编排层捕获处理（详见 §2.3）。
8. 不对并发 tool 调用设上限。

### 3.4 模块内部边界

`tools` 模块内部可继续拆实现，但不向外暴露为一级模块接口：

1. builtin tool providers（bash、task 等）。
2. MCP provider adapter（未来）。
3. tool routing（由 `ToolManager` 完成）。

对 `agent` 暴露的唯一稳定边界是 `ToolRegistry` Protocol。

内置 tool 的函数签名为：

```python
async def f(args: dict[str, JSONValue]) -> JSONValue:
    ...
```

### 3.5 内置 Bash Tool

- name: `bash`
- description: `Execute a shell command and return stdout, stderr and exit code`
- 参数：
  - `command` (string, required)：要执行的 shell 命令。
  - `cwd` (string, optional)：工作目录。
  - `env` (object, optional)：环境变量键值对。
  - `stdin` (string, optional)：标准输入内容。

返回结构：

```json
{"stdout": "<string>", "stderr": "<string>", "returncode": <int>}
```

超时时返回 `{"stdout": "", "stderr": "Command timed out after 30 seconds", "returncode": -1}`。

实现要点：

1. 使用 `asyncio.create_subprocess_shell` 异步执行命令。
2. 分别捕获 stdout 与 stderr，连同 returncode 作为 dict 返回，不合并。
3. 命令超时时间默认 30 秒，超时后 kill 进程并返回超时结构。
4. 命令执行失败（非零退出码）正常返回结构，不抛异常（让模型自行判断）。
5. `cwd` / `env` / `stdin` 通过 `create_subprocess_shell` 和 `communicate()` 传入。

注册方式：启动脚本先加载配置文件中的 `tools.providers` 列表，然后将 `BashToolProvider` append 到列表末尾，统一调用 `ToolManager.register()`。

### 3.6 内置 Task Tool

- name: `create_task`
- description: `Create a sub-task with its own session and execute it`
- 参数：
  - `prompt` (string, required)：子任务提示词。
  - `id` (int, optional)：子任务 id。
  - `depends` (array of int, optional)：子任务依赖。
  - `tools` (array of string, optional)：子任务可用的 tool 名称列表（默认可用全部）。
  - `inheritance` (bool, optional)：继承发起 task 的 chain，默认 `false`。

实现要点：

1. 子任务有独立的 `Session`，与主会话隔离。
2. 子任务执行完成后，结果（`output_text` 与 `stop_reason`）返回给主会话。
3. 子任务异常不影响主会话（异常被捕获并作为 failed 结果返回）。
4. `inheritance=true` 时，从当前 session 倒推到第一个没有 `frozen` 属性的 node 做 fork，加 `UserPromptNode`，然后执行。
5. 发起子任务后 tool call 不会超时；每个 task 有 300s 超时。
6. 子任务的 tool 集合排除 `create_task`，避免递归；子任务复用主 agent 与主 `ToolManager`，无需独立的 sub-ToolManager。

### 3.7 内置 Http Tool

- name: `http`
- description: `Send an HTTP request and return status, headers and body`
- 参数：
  - `url` (string, required)：请求 URL。
  - `method` (string, optional)：HTTP 方法，默认 `GET`。
  - `headers` (object, optional)：请求头键值对 `{k: v}`。
  - `body` (string, optional)：请求体。
  - `timeout` (number, optional)：超时秒数，默认 30。

返回结构：

```json
{"status": <int>, "headers": {"<k>": "<v>", ...}, "body": "<string>"}
```

网络错误时返回 `{"status": -1, "headers": {}, "body": "<error message>"}`。

实现要点：

1. 使用 `aiohttp.ClientSession` 发起异步请求。
2. 响应 headers 序列化为 `dict[str, str]`。
3. 响应 body 以 UTF-8 解码（`errors="replace"`）。
4. 超时与网络异常均捕获，返回 status=-1 结构，不抛异常。

---

### 3.8 内置 File Tools

#### write_file

- name: `write_file`
- description: `Write content to a file, creating parent directories as needed`
- 参数：
  - `path` (string, required)：目标文件路径。
  - `content` (string, required)：写入内容。
  - `encoding` (string, optional)：编码，默认 `utf-8`。

返回：成功时返回 `"Written <n> bytes to <path>"`；失败时返回错误信息字符串，不抛异常。

实现要点：

1. 写入前自动创建父目录（`Path.mkdir(parents=True, exist_ok=True)`）。
2. 以 `"w"` 模式覆盖写入。

#### edit_file

- name: `edit_file`
- description: `Replace an exact string in a file`
- 参数：
  - `path` (string, required)：目标文件路径。
  - `old_str` (string, required)：待替换的精确字符串。
  - `new_str` (string, required)：替换后的字符串。
  - `encoding` (string, optional)：编码，默认 `utf-8`。

返回：成功时返回 `"Replaced 1 occurrence in <path>"`；`old_str` 不存在时返回错误信息，不修改文件，不抛异常。

实现要点：

1. 读取全文，检查 `old_str` 是否存在；不存在直接返回错误。
2. 只替换第一次出现（`str.replace(old, new, 1)`），避免意外多替换。
3. 写回时使用相同编码。

---

## 4. ACP 协议与 Frontend

frontend 实现 `Client` 接口；`Agent` 在构造时持有 `Client` / `Backend` / `ToolRegistry`（以及可选的 `Compressor` / `PermissionManager` / `Memory`）引用；`Agent.new()` 与 `Agent.load()` 创建 `Session`；`Session.prompt()` 推进一轮对话；`Session` 通过 `Agent` 反向回调 `Client.update()`。

ACP `initialize`（能力协商）由 `Agent.__init__` 在构造时隐式完成，不单独建模。

### 4.1 共享类型

```python
JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
ContentBlock = dict[str, JSONValue]


StopReason = Literal["end_turn", "cancelled"]
PromptReturn = tuple[StopReason, str]


@dataclass(slots=True)
class SessionUpdate:
    type: Literal[
        "agent_message_chunk",
        "thinking_chunk",
        "tool_call",
        "tool_call_update",
    ]
    data: dict[str, JSONValue]
```

约束：

1. `agent_message_chunk` 是模型最终输出的显示内容；`thinking_chunk` 是模型的思考过程（如 reasoning）。CLI 中两者分离输出。
2. 每条消息在输出前 `strip()` 前后空白字符。
3. `prompt()` 失败时不返回 `failed`，而是直接抛异常，遵循 Python 风格。

### 4.2 Client 接口

```python
class Client(Protocol):
    async def update(self, session: "Session", update: SessionUpdate) -> None: ...
    async def request_permission(
        self,
        session: "Session",
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool: ...
```

ACP 映射：`update()` ↔ `session/update`；`request_permission()` ↔ `session/request_permission`。

约束：

1. 白名单、访问者鉴权等逻辑属于 frontend 或启动脚本，不属于 agent 核心。
2. terminal、filesystem 等能力优先建模为 tools，而非 client 方法。
3. `request_permission()` 在 DEBUG 级别记录 `kind` 和 `payload`，便于审计与调试。

### 4.3 Agent 接口

```python
class Agent(Protocol):
    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolRegistry,
        compressor: "Compressor | None" = None,
        permissions: "PermissionChecker",
        memory: "Memory | None" = None,
    ) -> None: ...

    async def new(self, cwd: str | None = None) -> "Session": ...
    async def load(self, data: JSONValue) -> "Session": ...
```

ACP 映射：`new()` ↔ `session/new`；`load()` ↔ `session/load`；`initialize` 由 `__init__` 隐式完成。

约束：

1. 如需绑定不同 client，应创建不同 agent 实例。
2. `compressor` / `memory` 为可选注入；`permissions` 必须注入，默认值为 `client`；详见 §2.6 / §2.7 / §2.8。
3. backends 支持多个，agent 只持有名为 `primary` 的那个；compressor 是否使用独立 backend，由配置中是否存在名为 `compressor` 的 backend 决定。

### 4.4 Session 接口

```python
class Session(Protocol):
    async def prompt(
        self,
        prompt: str | list[ContentBlock],
        allowed_tools: list[str] | None = None,
    ) -> PromptReturn: ...
    async def cancel(self) -> None: ...
    async def fork(self) -> "Session": ...
    async def compress(self) -> None: ...
    def save(self) -> JSONValue: ...
```

ACP 映射：`prompt()` ↔ `session/prompt`；`cancel()` ↔ `session/cancel`。`fork()` / `compress()` / `save()` 是项目扩展能力。

约束：

1. `allowed_tools=None` 表示使用全部已注册 tool；传入列表时本轮 backend 仅可见该子集，不在列表中的 tool 完全不出现在 tools 定义中。
2. backend 返回的 `tool_calls` 若包含不在允许列表中的 tool，按 §2.3 规则 4 写入失败结果，不实际执行。
3. `fork()` 不接收 `from_node_id`，语义为基于当前 session 状态浅拷贝式分叉（详见 §2.4）。
4. `compress()` 调用 agent 注入的 `Compressor`（详见 §2.6）。
5. `save()` 导出当前 session 状态；`load()` 由 agent 负责恢复。
6. `Session` 内部维护 pending prompt 队列，容量默认 3。活跃 turn 存在时，新的 `prompt()` 调用进入队列等待；队列满则抛 `SessionBusy`。
7. 活跃 turn 存在时调用 `fork()` 或 `compress()`，直接抛异常。

### 4.5 Frontends 模块边界

`frontends` 是模块边界，不再单独定义 `Frontend` 协议。各 frontend 只需实现 `Client`，再各自提供自己的 `run(agent)` 入口。

### 4.6 CliClient

职责：

1. 由启动脚本构造并注入 `agent`。
2. 创建或恢复 session；对 session 调用 `prompt()`。
3. 实现 `update()` 来消费通知并输出。
4. 处理取消、退出与 fork 命令。
5. readline 集成：方向键召回历史、指令历史持久化到 `~/.little_agent_history`、Tab 补全 `/` 命令。

#### stdin 架构

CliClient 通过 `_stdin_queue`（`asyncio.Queue[str | None]`, maxsize=32）解耦 stdin 阻塞读取与主循环处理：

```
asyncio.to_thread(stdin.readline)   ← 线程池阻塞，不卡事件循环
        ↓ (_stdin_reader 后台 task)
    _stdin_queue
    /           \
run() 主循环     _watch_cancel_loop
（agent 空闲时）  （prompt turn 运行时并发监听）
```

规则：

1. `_stdin_reader`：常驻后台 task，循环 `await asyncio.to_thread(sys.stdin.readline)`；EOF 时 put `None` 并退出；`run()` 结束时 cancel 并 await。
2. `run()` 主循环：agent 空闲时从 `_stdin_queue.get()` 取输入；slash 命令交 `_handle_command`，普通文本发给 `session.prompt()`。
3. `_watch_cancel_loop`：`_do_prompt` 启动时并发运行；监听队列中的 `/cancel`（调用 `session.cancel()`）；其他输入 put back 到队列末尾，让 `run()` 主循环在当前 prompt 结束后处理。注意：这意味着 prompt 期间的普通文本**不直接进入 `Session.pending_queue`**，而是在当前 turn 结束后才作为下一条 prompt 发出。
4. `_permission_done`（`asyncio.Event`，初始 set）：`request_permission` 在 `_stdin_queue.get()` 前 clear，finally 中 set；`_watch_cancel_loop` 在每次迭代开头检测 event；未 set 时等待其 set 或 prompt_task 结束，避免与 `request_permission` 争抢同一队列条目。
5. `_stdin_queue` 的 maxsize=32 作为兜底：防止 `_stdin_reader` 异常快速循环（如测试中 mock 错误）时无界增长导致 OOM。

显示规则：

1. 消息分离：`agent_message_chunk` 前缀 `[Agent]`；`thinking_chunk` 前缀 `[Thinking]` 或折叠显示。两者输出区域分离。
2. 空白处理：所有消息输出前 `strip()` 去前后空白。
3. Tool call 参数显示：`tool_call` 类型更新除显示 tool 名称外，以多行 `k: v` 格式显示参数（arguments）；字符串值直接输出，非字符串值退化为 `json.dumps`。参数文本超过 5 行时截断尾部并显示 `...{n} lines...`。

命令清单：

| 命令 | 作用 |
| --- | --- |
| `/quit` | 退出 CLI |
| `/exit` | `/quit` 的别名 |
| `/cancel` | 取消当前活跃 turn |
| `/fork` | 从当前 session 分叉出新 session |
| `/new` | 创建全新 session |
| `/save <path>` | 保存当前 session 到文件 |
| `/load <path>` | 从文件加载 session |
| `/list-tools` | 列出当前已注册的所有 tool 名称与描述 |

## 5. Backend

backend 负责将 session 节点链转换为各自 API 所需的消息格式，并将 API 响应映射回 `BackendTurnResult`。所有 backend 都是远程调用，不要求支持底层请求级 cancel。

### 5.1 共享类型

```python
@dataclass(slots=True)
class BackendToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class BackendTurnResult:
    output_text: str
    tool_calls: list[BackendToolCall]
    finish_reason: Literal["completed", "tool_call", "cancelled"]
    usage: dict[str, int] | None = None  # e.g. {"input_tokens": 100, "output_tokens": 50}
    thinking_text: str | None = None     # accumulated reasoning text (if model supports it)
```

### 5.2 Backend 接口

```python
from typing import AsyncIterator

class Backend(Protocol):
    def generate(self, session: "Session") -> AsyncIterator[SessionUpdate | BackendTurnResult]: ...
```

约束：

1. `generate()` 返回 `AsyncIterator`，先 yield 零到多个 `SessionUpdate`（`agent_message_chunk` 或 `thinking_chunk`），最后 yield 一个 `BackendTurnResult` 作为终止标记。
2. 消费方（`AgentCore._run_turn`）遍历 iterator：遇到 `SessionUpdate` 立即 `client.update()` 转发；遇到 `BackendTurnResult` 退出循环，处理 `finish_reason`。
3. backend 接收 `session` 对象，负责读取 session 链式历史并转换为后端的输入，同时把 session 当前可见的 tools 转换为后端需要的工具定义。
4. 流式 backend 使用 streaming API，逐 chunk yield `agent_message_chunk` / `thinking_chunk`，在流结束后 yield 最终的 `BackendTurnResult`。
5. 性能计数：在 `BackendTurnResult` yield 前记录 INFO 级别日志，包含 input/output token 数、执行时间、缓存信息。
6. DEBUG 日志：请求开始前记录完整 payload（messages、tools 等）。
7. 超时控制：streaming 模式下对整个流设置超时，超时后关闭 stream 并抛 `BackendTimeoutError`。
8. context-overflow 异常：底层 API 返回上下文长度超限错误时，backend 必须识别并抛 `ContextOverflowError`（定义在 `backends/exceptions.py`），由 agent core 按 §2.6.4 处理。其他 `BadRequestError` 原样向上抛。
9. `BackendTurnResult.thinking_text` 保留字段（用于非流式 fallback 或测试），流式模式下通常为 `None`（thinking 已通过 `thinking_chunk` 逐 chunk 发出）。
10. `<think>` 标签处理：部分模型（如 DeepSeek-R1）不使用 `reasoning_content` 字段，而是在 `content` 中以 `<think>...</think>` 标签包裹思考。`OpenAIBackend` 在 streaming 中维护跨 chunk 状态机：标签外内容作为 `agent_message_chunk` emit，标签内作为 `thinking_chunk` emit；流结束时未闭合的 `<think>` 按 `thinking_chunk` 处理。`reasoning_content` 路径不受影响。

### 5.3 并发控制

规则：

1. 每个 `Backend` 实例在构造时根据配置项 `max_concurrency` 初始化一把 `asyncio.Semaphore`；默认 `1`，表示串行。
2. 所有 `generate()` 调用必须在内部 acquire 该 semaphore，调用完成（无论成功、异常、取消）后 release。
3. 调用方可以并发发起 `generate()`（如 `asyncio.gather`），实际并发由 backend 的 semaphore gate。
4. Semaphore 的获取与释放对调用方透明，不暴露在接口签名上。

### 5.4 AnthropicBackend 专项说明

`AnthropicBackend` 使用 `anthropic` Python SDK，与 `OpenAIBackend` 的主要差异如下。

#### 5.4.1 配置参数

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | — | 固定为 `anthropic` |
| `model` | string | — | 必填，如 `claude-opus-4-7` |
| `api_key` | string | — | 与 `api_key_env` 二选一 |
| `api_key_env` | string | — | 环境变量名，与 `api_key` 二选一 |
| `system` | string | `null` | System prompt，不属于对话历史 |
| `context_window` | int | 128000 | 同时作为 `max_tokens` 上限（Anthropic 必填） |
| `max_concurrency` | int | 1 | 并发控制，同 §5.3 |
| `base_url` | string | `null` | 可选，自定义 API 地址 |

`max_tokens` 直接使用 `context_window` 值，无需单独配置。

#### 5.4.2 节点链 → Anthropic 消息转换

| 节点类型 | 转换规则 |
|----------|----------|
| `UserPromptNode` | `{"role": "user", "content": prompt}` |
| `AssistantResponseNode`（无后续 ToolCallNode）| `{"role": "assistant", "content": [{"type": "text", "text": text}]}` |
| `AssistantResponseNode` + `ToolCallNode`（相邻） | 合并为一条 `role: assistant` 消息，content 包含 text 块（可选）+ tool_use 块 |
| `ToolCallNode`（无前置文本） | `{"role": "assistant", "content": [{"type": "tool_use", "id": call_id, "name": ..., "input": ...}, ...]}` |
| `ToolResultNode` | `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": result_str}, ...]}` |
| `SummaryNode` | `{"role": "user", "content": summary_text}` |

约束：

1. `ToolResultNode.results[call_id]["content"]` 若为字符串直接使用，否则 `json.dumps`。
2. Anthropic 要求 assistant message 与 user message 严格交替；`ToolResultNode` 必须紧接 `ToolCallNode` 所在的 assistant message 之后，作为 user message。
3. `system` 参数通过独立字段传入 API，不进 messages 数组。

#### 5.4.3 工具定义格式

Anthropic 的工具定义使用 `input_schema`（JSON Schema）：

```json
{
  "name": "bash",
  "description": "Execute a shell command",
  "input_schema": {
    "type": "object",
    "properties": {
      "command": {"type": "string", "description": "..."}
    },
    "required": ["command"]
  }
}
```

由 `ToolMap` 转换而来（对应 OpenAI backend 的 `_tool_map_to_openai_functions`）。

#### 5.4.4 流式事件处理

使用 `client.messages.stream()` 上下文管理器。事件映射：

| Anthropic 事件 | emit 类型 |
|----------------|-----------|
| `content_block_start` / `content_block_delta`（`text_delta`） | `agent_message_chunk` |
| `content_block_start` / `content_block_delta`（`thinking_delta`） | `thinking_chunk` |
| `content_block_delta`（`input_json_delta`） | 累积到当前 tool_use block，不 emit |
| `message_stop` | 触发 yield `BackendTurnResult` |

不使用 `<think>` 标签解析（该逻辑仅属于 `OpenAIBackend`）。

#### 5.4.5 finish_reason 映射

| Anthropic `stop_reason` | `BackendTurnResult.finish_reason` |
|-------------------------|-----------------------------------|
| `end_turn` | `completed` |
| `tool_use` | `tool_call` |

#### 5.4.6 Context overflow 检测

捕获 `anthropic.BadRequestError`，检查 message 是否匹配以下 pattern（大小写不敏感）：

- `"prompt is too long"`
- `"too many tokens"`
- `"maximum context length"`

匹配时 raise `ContextOverflowError`，其他 `BadRequestError` 原样向上抛。

## 6. 其他

### 6.1 启动脚本

通过 `pyproject.toml` 的 `[project.scripts]` 注册：

```toml
[project.scripts]
little-agent = "little_agent.main:main"
```

`main()` 放在 `little_agent/main.py`。装配层不承载业务逻辑。

职责：

1. 解析 CLI 参数（`--config`、`--loglevel` 等）。
2. 加载 YAML 配置文件。
3. 初始化 logger：
   - 配置中存在 `cfg['logging']` 时，使用 `logging.config.dictConfig(cfg['logging'])`。
   - 否则使用内置 `_DEFAULT_LOGGING_CONFIG` 标准化 dictConfig。
   - `--loglevel` 强制覆盖 `cfg['logging']['loggers']['']['level']`。
4. 初始化 `ToolManager`：构造实例；加载配置中的 providers，将 `BashToolProvider` append 到末尾，统一注册。
5. 初始化各 `Backend`（按配置中 `backends` 多个名称分别构造）。
6. 初始化 `Compressor`（可选）、`Memory`（可选）。
7. 初始化具体 `Client` 实现。
8. 从配置 `permissions` list 与 `client` 构建 permission chain（`PermissionChecker`）；list 为空则直接用 `client`。
9. 用上述依赖构造 `Agent`。
9. 调用 client 的 `run(agent)` 启动交互。

### 6.2 配置文件 schema

YAML 格式。最小 schema：

```yaml
backends:
  primary:
    type: openai                         # 或 anthropic
    model: gpt-4
    api_key: OPENAI_API_KEY
    base_url: https://api.openai.com/v1  # optional
    context_window: 128000               # optional, default 128000；anthropic 同时用作 max_tokens
    max_concurrency: 1                   # optional, default 1
  # Anthropic backend 示例：
  # primary:
  #   type: anthropic
  #   model: claude-opus-4-7
  #   api_key: sk-ant-...               # 或 api_key_env: ANTHROPIC_API_KEY
  #   system: "You are a helpful assistant."  # optional, default null
  #   context_window: 200000            # optional, default 128000
  #   max_concurrency: 1
  compressor:
    type: openai
    model: gpt-3.5-turbo
    api_key_env: OPENAI_API_KEY_NAME_IN_ENV
    context_window: 128000
    max_concurrency: 1

agent:
  R: 0.5                                 # post-turn 触发阈值，取值范围 (0, 1]，默认 0.5

compressor:
  keep_turns: 5                          # 不参与压缩的最近 turn 数，下限 3，默认 5
  compressed_window: 0.2                 # 压缩历史上限比例，W = compressed_window * primary.context_window，默认 0.2

tools:
  providers:
    - type: python
      module: my_tools.weather
    - type: python
      module: my_tools.calculator

# permissions 为 checker 列表，从上到下依次检查，首个能决策的截断 chain。
# 列表为空或省略时，所有 tool 调用直接询问用户（client）。
permissions:
  - type: blackwhitelist
    blacklist:
      - "dangerous_*"     # fnmatch 模式，命中则立即 deny
    whitelist:
      - "read_*"          # fnmatch 模式，命中则立即 allow
  - type: yesman          # 放行所有未被上面拦截的请求

frontend:
  type: cli

logging:
  version: 1
  disable_existing_loggers: false
  formatters:
    default:
      format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  handlers:
    console:
      class: logging.StreamHandler
      formatter: default
      stream: ext://sys.stdout
  loggers:
    "":
      level: INFO
      handlers: [console]
```

### 6.3 测试设计

测试原则：

1. 各模块在封装完成前应保持分散，方便单测。
2. 模块边界足够稳定，才能用 mock 替代真实依赖。

必须提供的 mock 实现：

1. `MockClient`：实现 `Client` 接口；收集 `SessionUpdate` 与 prompt 结果；不依赖终端交互。
2. `MockToolProvider`：实现 `ToolProvider` 接口；返回固定 `ToolMap`；按预设规则返回 JSON 可序列化结果；支持模拟成功、失败、延迟、取消后迟到结果。
3. `MockBackend`：按预设脚本返回文本或 tool calls；支持模拟多轮 tool use、取消、失败。
4. `MockAgent`：暴露与 `Agent` 一致的 `new()` / `load()` 接口；主要给 frontends 与 tools 的集成测试使用。

测试分层：

1. **模块单元测试**：覆盖每个模块内部逻辑。
   - `agent`：倒排链、freeze、fork、cancel、compress 规则。
   - `tools`：list/invoke/聚合行为。
   - `backends`：请求转换、返回解析。
2. **模块集成测试**：被测模块保留真实实现，所有上下游接口换成 mock。
   - 测 `agent`：`MockClient + Agent + MockToolProvider + MockBackend`。
   - 测 `frontends`：`CliClient + MockAgent`。
   - 测 `tools`：`MockAgent` 驱动 + 真实 `ToolManager` + 真实 provider。
   - 测 `backends`：真实 `Backend` + 预构造的真实 `Session` 对象。

第一批必须覆盖的关键用例：

1. 无 tool 的单轮对话。
2. 一轮中单个 tool call。
3. 一轮中多个并行 tool calls。
4. 多轮 backend-tool 循环。
5. tool 执行抛异常时，失败进入 `ToolResultNode.results`，模型继续推理。
6. tool call 进行中触发 cancel。
7. cancel 后迟到 tool result 被丢弃。
8. 从当前 session fork 出新 session。
9. 有活跃 turn 时调用 `fork()` 或 `compress()` 抛异常。
10. 有活跃 turn 时再次 `prompt()`，进入 pending 队列；队列满抛 `SessionBusy`。
11. 超过 `MAX_TURN_ITERATIONS` 抛异常。

### 6.4 已知限制

1. `ToolArgDef` 只支持顶层 object + 一层平铺标量字段，不支持嵌套、数组、枚举、默认值。
2. 不对并行 tool 调用设并发上限。
3. `save()` / `load()` 的详细 schema 未完全确定；只确定需要序列化节点链表，其他字段随实现确定。
