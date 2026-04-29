# 设计文档

## 1. 目标

本期先完成最小可运行 Agent 系统的接口设计与模块边界设计，再进入实现。

当前已确定的前提如下：

1. 最小目标是"对话 + tools = agent"。
2. 内核采用 `asyncio`。
3. 架构上与 ACP 保持等效语义，但同进程内不机械复制 JSON-RPC 包装。
4. 长期存在三个 frontend：`cli`、`web`、`acp`，本期只实现 `cli`。
5. tool 通过配置文件注册，tool 描述尽量对齐 MCP。
6. backends 本期只支持 OpenAI API。
7. 对话历史采用倒排链，运行时优先使用对象引用。

## 2. 模块划分

一级模块四个：

1. `agent`
   - 系统核心。
   - 维护会话、分支、倒排链、取消、冻结、fork、压缩。
   - 对 frontend 暴露 ACP 类接口。
   - 调用 backend 获取模型输出。
   - 调用 tools 执行工具。
2. `tools`
   - 对 agent 暴露 MCP 类接口。
   - 负责 tool 注册、筛选、调用。
   - 负责内置 tool 与 MCP tool provider 的统一接入。
3. `frontends`
   - 负责用户交互。
   - 本期只实现 `cli`。
   - 后续扩展 `web` 与原生 `acp`。
4. `backends`
   - 负责具体模型供应商接入。
   - 本期只实现 OpenAI backend。

系统启动由一个命令行脚本 `little-agent` 完成装配：加载 YAML 配置、初始化 logger、初始化各模块、拼装依赖、启动 client。脚本通过 `pyproject.toml` 的 `[project.scripts]` 注册，不是一级模块，只是装配层。

说明：

1. `session`、`chain`、`persistence` 不作为一级模块暴露。
2. 它们是 `agent` 模块的内部实现。
3. 在正式封装前，各模块保持分散状态，便于单测与替换。

## 3. 模块关系

模块之间的边界如下：

1. `frontends <-> agent`
   - ACP 类接口。
2. `tools <-> agent`
   - MCP 类接口。
3. `backends <-> agent`
   - 项目内部接口，本期先做最小化定义。
4. 启动脚本 `-> all`
   - 只负责装配，不承载业务逻辑。

总体依赖方向如下：

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

1. `agent` 不直接依赖具体 frontend 实现。
2. `agent` 不直接依赖具体 backend 实现。
3. `agent` 不直接依赖具体 tool 实现。
4. 启动脚本负责把具体实现注入到协议接口上。

## 4. frontends 与 agent 的 ACP 类接口

### 4.1 设计原则

这一层采用更符合 Python 使用习惯的对象模型：

1. frontend 具体实现 `Client` 接口。
2. `Agent` 在构造时持有 `Client`、`Backend`、`ToolProvider`（以及可选的 `Compressor`）引用。
3. `Agent.new()` 与 `Agent.load()` 创建 `Session`。
4. `Session.prompt()` 负责推进一轮对话，也就是延伸倒排链。
5. `Session` 在运行中通过 `Agent` 反向回调 `Client.update()`。

这样设计的原因是：

1. `Agent` 已经在构造时绑定了唯一的 `Client`，因此 `new()` 与 `load()` 无需再次传入 `client`。
2. 如果需要绑定不同的 frontend/client，应创建不同的 agent 实例。
3. 每个 agent 实例都是有状态的 stateful agent；其核心状态是它所管理的 sessions。
4. ACP 的 `initialize`（能力协商）由 `Agent.__init__` 在构造时隐式完成，不单独建模。目的是消除"未初始化对象"这种在同进程内意义不大的中间状态。

### 4.2 共享类型

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
        "tool_call",
        "tool_call_update",
    ]
    data: dict[str, JSONValue]
```

说明：

1. `SessionUpdate` 是 client/frontend 观察到的事件。
2. `agent_message_chunk` 只是一种通知语义，不要求在历史链中物化成独立节点。
3. 当前先主要实现 `update()`；`request_permission()` 先留接口，不在本期真正启用。
4. `prompt()` 失败时不返回 `failed`，而是直接抛异常，遵循 Python 风格。

### 4.3 Client 接口

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

语义映射：

1. `update()` 对应 ACP `session/update`
2. `request_permission()` 对应 ACP `session/request_permission`

说明：

1. `update` 应当是 client 的方法，而不是 agent 的方法。
2. 白名单、访问者鉴权等逻辑属于 frontend 或启动脚本，不属于 agent 核心。
3. terminal、filesystem 等能力在本项目里优先建模为 tools，而不是 client 方法。

### 4.4 Agent 接口

```python
class Agent(Protocol):
    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolProvider,
        compressor: "Compressor | None" = None,
    ) -> None: ...

    async def new(self, cwd: str | None = None) -> "Session": ...
    async def load(self, data: JSONValue) -> "Session": ...
```

语义映射：

1. `new()` 对应 ACP `session/new`
2. `load()` 对应 ACP `session/load`
3. ACP `initialize` 由 `__init__` 隐式完成

说明：

1. `Agent` 在构造时完成依赖绑定，消除"未初始化对象"中间状态。
2. `new()` 与 `load()` 不重复接收 `client` 参数。
3. 如需不同 client，应创建不同 agent 实例。
4. `compressor` 为可选注入；不注入时 `Session.compress()` 抛异常。
5. `tools` 参数类型为 `ToolProvider`。Agent 运行时只关心"能列出工具、能调用工具"，不关心对方是单个 provider 还是聚合后的 `ToolManager`。

### 4.5 Session 接口

```python
class Session(Protocol):
    async def prompt(self, prompt: str | list[ContentBlock]) -> PromptReturn: ...
    async def cancel(self) -> None: ...
    async def fork(self) -> "Session": ...
    async def compress(self) -> None: ...
    def save(self) -> JSONValue: ...
```

语义映射：

1. `prompt()` 对应 ACP `session/prompt`
2. `cancel()` 对应 ACP `session/cancel`
3. `fork()`、`compress()`、`save()` 是项目扩展能力

说明：

1. 本期不接收 `allowed_tool_names` 参数；agent 对本轮可见全部已注册 tools。运行时动态 tool 选择能力推迟到后续版本，届时以新参数或 Session 级别的配置接入。
2. `fork()` 不接收 `from_node_id`，避免把低频且复杂的节点选择暴露给调用方。
3. `fork()` 的语义就是基于当前 session 状态进行浅拷贝式分叉。
4. `compress()` 调用 agent 注入的 `Compressor`，把 session 的 tail 替换为压缩后的链头。
5. `save()` 导出当前 session 状态；`load()` 由 agent 负责恢复。
6. `Session` 内部维护一个 pending prompt 队列，容量默认 3（允许短时多句追加，超出即视为滥用）。在活跃 turn 存在时，新的 `prompt()` 调用进入队列等待；队列满则抛 `SessionBusy` 异常。
7. 活跃 turn 存在时调用 `fork()` 或 `compress()`，直接抛异常。

### 4.6 frontends 模块说明

`frontends` 是模块边界，不再单独定义一个稳定的 `Frontend` 协议。

原因：

1. 当前真正稳定的边界是 `Client`。
2. 各 frontend 只需要实现 `Client`，再各自提供自己的 `run(agent)` 入口即可。
3. `run(agent)` 不足以单独构成一个值得长期稳定的跨模块协议。

本期实现为 `CliClient`，其职责如下：

1. 由启动脚本构造并注入 `agent`。
2. 创建或恢复 session。
3. 对 session 调用 `prompt()`。
4. 实现 `update()` 来消费通知并输出。
5. 处理取消、退出与后续 fork 命令。

## 5. tools 与 agent 的 MCP 类接口

### 5.1 设计原则

agent 不应关心 tool 的具体来源。

无论 tool 是：

1. 内置 Python 实现
2. 配置文件加载的插件
3. 后续接入的 MCP provider

对 agent 来说都应统一为一组 MCP 类能力：列出工具、调用工具。

### 5.2 Tool 共享类型

```python
JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

ToolArgDef = tuple[str, str, str, bool]
ToolDef = tuple[str, list[ToolArgDef]]
ToolMap = dict[str, ToolDef]
```

说明：

1. `ToolArgDef` 的四元组顺序为 `(name, type, desc, required)`。
2. `ToolDef` 的二元组顺序为 `(desc, args)`。
3. `ToolMap` 的 key 是 tool name，value 是对应的 `ToolDef`。
4. `ToolMap` 这样设计是为了便于在 Python 中直接 `dict.update(...)` 做聚合。
5. `ToolArgDef` 可自动转换成最小 MCP `inputSchema`：
   - 顶层固定为 `type: "object"`
   - 字段填入 `properties`
   - `required` 列表由四元组中的 `required` 推导
6. 当前只支持顶层 object + 一层平铺标量字段；不支持嵌套对象、数组、枚举、默认值。本期已知限制（见 §11），`ToolArgDef` 未来会重新设计。

额外约束：

1. tool 输入与输出都必须可 JSON 序列化。
2. 框架层通过 `json.dumps(...)` 校验可序列化性。
3. `session_id`、`cwd`、`call_id` 不进入 tool 函数签名；这些由 agent 内部管理。

### 5.3 ToolProvider 接口

```python
@runtime_checkable
class ToolProvider(Protocol):
    def list(self) -> ToolMap: ...
    async def invoke(self, name: str, **kwargs: JSONValue) -> JSONValue: ...
```

规则：

1. `list()` 返回当前 provider 暴露的全部 tools。
2. `invoke()` 是 async 的，以便 agent 用 `asyncio.gather` 并发执行多个 tool call。同步 tool 由 provider 层用 `asyncio.to_thread` 包装成 async。
3. `invoke()` 的签名与底层 tool 函数一致，便于透传与测试。
4. `invoke()` 的返回值不限定为字符串，只要求可 JSON 序列化。
5. 未知 tool、参数不合法、执行失败都通过异常表示，不使用额外的错误码返回机制。
6. 建议内部至少区分两类异常：
   - `ToolInvokeError`：调用层错误，例如未知 tool、参数不合法
   - `ToolExecutionError`：tool 自身执行失败
7. 上述异常在 agent 编排层被捕获，落入 `ToolResultNode` 对应 `call_id` 的 `status = "failed"` 结果中，**绝不向上冒出 prompt turn**。这是 tools 机制的关键语义：模型拿到失败反馈后，自主决定是否重试、换工具或放弃。
8. 本期不对并发 tool 调用设上限；未来可能加入并发上限（见 §11）。

### 5.4 ToolManager 实现

`ToolManager` 是一个**具体类**，不是 Protocol。它聚合多个 `ToolProvider`，对外实现 `ToolProvider` Protocol（即提供 `list()` 和 `invoke()`），同时额外提供 `register(provider)` 方法用于组装期注册。

说明：

1. `ToolProvider` 是 agent 运行时的统一契约。任何实现了 `list` + `invoke` 的对象都可以注入 Agent。
2. 由于 `ToolMap` 是字典结构，聚合时可以直接 `tools.update(provider.list())`。
3. 这种设计支持 Chain of Responsibility 模式：可以在 `ToolManager` 外再包一层 filter、logger、权限检查等装饰层，只要外层也实现 `ToolProvider` 即可注入 Agent。

### 5.5 tools 模块内部实现边界

`tools` 模块内部可以继续拆实现，但不向外暴露为一级模块接口：

1. builtin tool registry
2. MCP provider adapter
3. tool routing

对 `agent` 暴露的唯一稳定边界就是 `ToolProvider` Protocol。

内置 tool 的最小函数形态为：

```python
async def f(**kwargs: JSONValue) -> JSONValue:
    ...
```

同步 tool 由内置 provider 统一包装成 async（`asyncio.to_thread`）。

## 6. backends 与 agent 的接口

### 6.1 设计原则

这层接口本期先保持最小化。

原因：

1. 只有 OpenAI backend 一个实现。
2. session 链如何转成 OpenAI 请求，需要先通过实现验证。
3. 因此不宜现在做过重抽象。
4. 当前所有 backend 都是远程调用，不要求支持底层请求级 cancel。

### 6.2 Backend 共享类型

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
```

### 6.3 Backend 接口

```python
class Backend(Protocol):
    async def generate(self, session: "Session") -> BackendTurnResult: ...
```

说明：

1. backend 接收 `session` 对象，而不是单独的 `tail` 或 `cancel_event`。
2. backend 负责读取 session 的链式历史，并转换为真实后端的输入。
3. backend 负责把 session 当前可见的 tools 转换为 OpenAI 需要的工具定义。
4. 本期 **backend 不做 streaming**；`generate()` 返回完整 `BackendTurnResult`。`agent_message_chunk` 由 agent 在拿到结果后一次性发出一次 update。
5. 如果后续实现 streaming，再把输入输出都调整为 async generator 风格。

## 7. agent 模块内部数据结构

下面这些结构属于 `agent` 的内部实现，但需要先在设计文档里明确，因为它们决定了整个系统的行为。

### 7.1 倒排链节点

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

1. 运行时通过 `prev` 对象引用回溯。
2. `id` 主要用于 save/load、日志、调试和 fork 入口。
3. 节点整体逻辑 append-only。
4. `frozen` 字段只出现在写入过程中可变的节点类型上：`AssistantResponseNode` 与 `ToolResultNode`。`UserPromptNode`、`ToolCallNode`、`SummaryNode` 创建即不可变，无需 `frozen` 字段。
5. 可变节点在任意时刻只能被一个 session 作为活跃尾节点持有。
6. 触发冻结的时机（由 Session 负责管理）：
   - session 追加新节点时，旧尾若为可变类型，立刻冻结；
   - session 被 fork（失去唯一引用）时，当前尾若为可变类型，立刻冻结；
   - 当前 turn 结束或被取消时，尾节点立刻冻结。

### 7.2 Session 对象状态

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

### 7.3 Tool Call 与 Tool Result 节点约束

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
4. tool 执行抛出的 `ToolInvokeError` / `ToolExecutionError` 在编排层被捕获，写入对应 `call_id` 的结果中（`status = "failed"`，`content` 为异常信息），**绝不向上冒出 prompt turn**。模型拿到失败反馈后自主决定下一步。
5. 若执行中被取消，`ToolResultNode` 中尚未完成的 call 标记为 `cancelled`，节点立刻冻结。
6. 节点冻结之后到达的迟到结果直接丢弃。

### 7.4 fork 规则

1. `session.fork()` 基于当前 session 状态创建一个新 session。
2. 新旧 session 共享已有历史节点。
3. fork 前如果当前尾节点仍可变，必须先冻结，再进行浅拷贝式分叉。
4. fork 时如果当前 session 存在活跃 turn，直接抛异常。
5. `fork()` 不暴露 `from_node_id` 参数。
6. 如果未来确实需要"从指定历史节点分叉"，再以新扩展方法加入。

### 7.5 压缩接口

压缩能力以可插拔协议定义，本期只预留接口、不提供具体实现：

```python
class Compressor(Protocol):
    async def compress(self, head: Node) -> Node: ...
```

规则：

1. 输入：要压缩的链头节点（含通过 `prev` 可达的全部历史）。
2. 输出：新的链头节点（通常是 `SummaryNode`，但协议不强制）。
3. `Compressor` 由启动脚本按配置构造，并在 `Agent.__init__` 注入。
4. `Session.compress()` 的语义：
   - agent 未注入 compressor：抛异常。
   - 活跃 turn 存在：抛异常。
   - 否则调用 `compressor.compress(tail)`，把返回节点设为 session 新的 tail。
5. 旧链保留，用于回放与 fork。不修改旧链，不从旧链摘节点。

## 8. agent 的编排流程

`Session.prompt()` 的编排流程如下：

1. 若当前 session 已有活跃 turn：进入 pending 队列；队列满则抛 `SessionBusy`。否则立刻占据，标记"有活跃 turn"。
2. 在当前尾部追加 `UserPromptNode`，旧尾若为可变类型先冻结。
3. 进入主循环（循环上限 `MAX_TURN_ITERATIONS`，默认 10）：
   1. 调用 `Backend.generate(session)`。
   2. 若 `finish_reason == "completed"`：
      - 追加或更新 `AssistantResponseNode`，追加完冻结。
      - 通过 `Client.update(session, agent_message_chunk)` 一次性发出最终文本（本期非 streaming）。
      - 跳出循环，返回 `("end_turn", output_text)`。
   3. 若 `finish_reason == "tool_call"`：
      - 追加 `ToolCallNode`（冻结）。
      - 通过 `Client.update(session, tool_call)` 通知 frontend。
      - 追加 `ToolResultNode`（可变）。
      - 并发调用 `ToolProvider.invoke(...)` 执行全部 tools（`asyncio.gather`）。
        - 正常完成：写入对应 `call_id` 的结果（`status = "completed"`）。
        - 抛出 `ToolInvokeError` / `ToolExecutionError`：捕获并写入失败结果（`status = "failed"`，`content` 为异常信息）。
        - tool 抛出的异常**绝不冒出 prompt turn**。
      - 每个结果就位通过 `Client.update(session, tool_call_update)` 通知 frontend。
      - 全部结果到位或 turn 被取消后，`ToolResultNode` 冻结。
      - 进入下一次循环。
   4. 若 `finish_reason == "cancelled"`：跳出循环，返回 `("cancelled", partial_output)`。
4. 超过 `MAX_TURN_ITERATIONS`：抛异常（视为真正失败）。
5. 过程中任意时刻收到 cancel：
   - 若正在等待 backend 返回：等当前调用自然结束，不再进入下一轮循环。
   - 若正在并发执行 tools：`asyncio.gather` 的 wait 被解除，已完成的结果正常写入，尚未完成的 call 在 `ToolResultNode.results` 中标记 `cancelled`，节点立刻冻结；后到的结果因节点已冻结而被丢弃。
   - 最后冻结任何未封口节点，返回 `("cancelled", partial_output)`。
6. 真正失败（backend 异常、链条不一致等）直接抛异常，而不是返回 `failed`。
7. 无论成功、取消还是异常，finally 清理活跃 turn 标记；pending 队列非空时唤醒下一个排队协程继续处理（失败不得污染队列）。
8. `Session.cancel()` 只影响当前活跃 turn，不清空 pending 队列。

`Session.cancel()` 的规则：

1. 如果 session 没有活跃 turn，直接返回。
2. 如果有活跃 turn，只设置"已请求取消"标记。
3. 真正的停止、冻结与收尾由 `prompt()` 所在协程完成。

## 9. 启动脚本

启动装配是最顶层的一层，不属于任何一级模块。通过 `pyproject.toml` 的 `[project.scripts]` 注册为一个名为 `little-agent` 的命令：

```toml
[project.scripts]
little-agent = "little_agent.main:main"
```

实际的 `main()` 函数放在一个独立模块（建议 `little_agent/main.py`）。用户 shell 下运行 `little-agent` 即调用该函数。

### 9.1 职责

1. 解析 CLI 参数（包括 `--debug` 等日志级别 flag）。
2. 加载 YAML 配置文件。
3. 初始化 logger（标准 `logging` 模块；debug 模式由 argparse flag 控制，符合 AGENTS.md 工程要求）。
4. 初始化 `ToolManager`：构造 `ToolManager` 具体实例，并调用其 `register()` 方法注册所有已配置的 providers。
5. 初始化 `Backend`。
6. 初始化 `Compressor`（可选）。
7. 初始化具体 `Client` 实现（本期为 `CliClient`）。
8. 用上述依赖构造 `Agent`。
9. 调用 client 的 `run(agent)` 启动交互。

不承载业务逻辑。

### 9.2 配置文件 schema

本期使用 YAML。最小 schema（实现时可按需扩展）：

```yaml
backend:
  type: openai
  model: gpt-4
  api_key_env: OPENAI_API_KEY

tools:
  providers:
    - type: python
      module: my_tools.weather
    - type: python
      module: my_tools.calculator

frontend:
  type: cli

logging:
  level: INFO
```

## 10. 测试设计

测试设计需要和模块边界一起确定，因为这直接影响后续开发方式。

### 10.1 测试原则

1. 各模块在封装完成前应保持分散，方便单测。
2. 模块边界必须足够稳定，才能用 mock 替代真实依赖。
3. 测试不仅用于验收，也用于反推 backend 与模型实际需要的行为。

### 10.2 必须提供的 mock 实现

1. `MockClient`
   - 实现 `Client` 接口。
   - 收集 `SessionUpdate` 与 prompt 结果。
   - 不依赖终端交互。
2. `MockToolProvider`
   - 实现 `ToolProvider` 接口。
   - 返回固定 `ToolMap`。
   - 按预设规则返回 JSON 可序列化结果。
   - 支持模拟成功、失败、延迟、取消后迟到结果。
3. `MockBackend`
   - 按预设脚本返回文本或 tool calls。
   - 支持模拟多轮 tool use。
   - 支持模拟取消和失败。
4. `MockAgent`
   - 暴露与 `Agent` 一致的 `new()` / `load()` 接口，返回可脚本化的 `MockSession`。
   - 主要给 frontends 与 tools 的集成测试使用，让它们脱离 agent 内部实现做独立验证。

### 10.3 测试分层

两类测试：

1. **模块单元测试**：覆盖每个模块内部逻辑。
   - `agent`：倒排链、freeze、fork、cancel、compress 规则。
   - `tools`：list/invoke/聚合行为。
   - `backends`：请求转换、返回解析。
2. **模块集成测试**：被测模块保留真实实现，其所有上下游接口换成 mock。
   - 测 `agent`：`MockClient + Agent + MockToolProvider + MockBackend`。
   - 测 `frontends`：`CliClient + MockAgent`。
   - 测 `tools`：`MockAgent` 驱动 + 真实 `ToolManager` + 真实 provider。
   - 测 `backends`：真实 `Backend` + 预构造的真实 `Session` 对象。不走 MockAgent，因为 Backend 依赖 session 链条的具体形态，MockAgent 难以替代。

### 10.4 第一批关键用例

第一批必须覆盖：

1. 无 tool 的单轮对话。
2. 一轮中单个 tool call。
3. 一轮中多个并行 tool calls。
4. 多轮 backend-tool 循环（模型连续多次请求 tool 直到完成）。
5. tool 执行抛异常时，失败进入 `ToolResultNode.results`，模型继续推理，异常不冒出 prompt turn。
6. tool call 进行中触发 cancel。
7. cancel 后迟到 tool result 被丢弃。
8. 从当前 session fork 出新 session。
9. 有活跃 turn 时调用 `fork()` 或 `compress()` 抛异常。
10. 有活跃 turn 时再次 `prompt()`，进入 pending 队列；队列满抛 `SessionBusy`。
11. 超过 `MAX_TURN_ITERATIONS` 抛异常。

## 11. 本期已知限制

1. `ToolArgDef` 只支持顶层 object + 一层平铺标量字段，不支持嵌套、数组、枚举、默认值。未来会重新设计。
2. Backend 不做 streaming；`agent_message_chunk` 一次性发出。
3. 不做运行时动态 tool 子集选择；所有已注册 tool 对 agent 始终可见。后续版本再加入"启动时配置开关"与"运行时动态切换"。
4. 不对并行 tool 调用设并发上限。未来可能加入。
5. `save()`/`load()` 的详细 schema 本期不定；只确定需要序列化节点链表，其他字段随实现确定。
6. `Client.request_permission()` 预留接口不启用。

## 12. 当前结论

当前准备按以下结构推进实现：

1. 一级模块固定为 `agent`、`tools`、`frontends`、`backends`
2. 启动装配由 `little-agent` 命令行脚本完成（`pyproject.toml` 的 `[project.scripts]` 注册）
3. `frontends <-> agent` 用 ACP 类接口；`Client` 是稳定边界
4. `tools <-> agent` 用 MCP 类接口；`ToolProvider` 是稳定边界
5. `backends <-> agent` 先使用最小内部接口
6. 测试中提供 `MockClient`、`MockToolProvider`、`MockBackend`、`MockAgent`
