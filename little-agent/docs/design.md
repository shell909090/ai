# 设计文档

## 1. 目标

本期先完成最小可运行 Agent 系统的接口设计与模块边界设计，再进入实现。

当前已确定的前提如下：

1. 最小目标是“对话 + tools = agent”。
2. 内核采用 `asyncio`。
3. 架构上与 ACP 保持等效语义，但同进程内不机械复制 JSON-RPC 包装。
4. 长期存在三个 frontend：`cli`、`web`、`acp`，本期只实现 `cli`。
5. tool 通过配置文件注册，tool 描述尽量对齐 MCP。
6. backends 本期只支持 OpenAI API。
7. 对话历史采用倒排链，运行时优先使用对象引用。

## 2. 模块划分

一级模块只保留五个：

1. `agent`
   - 系统核心。
   - 维护会话、分支、倒排链、取消、冻结、fork。
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
5. `entry`
   - 最终封装层。
   - 负责加载 config、初始化各模块、拼装依赖、启动执行。

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
4. `entry -> all`
   - 只负责装配，不承载业务逻辑。

总体依赖方向如下：

```text
entry
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
4. `entry` 负责把具体实现注入到协议接口上。

## 4. frontends 与 agent 的 ACP 类接口

### 4.1 设计原则

这一层采用更符合 Python 使用习惯的对象模型：

1. frontend 具体实现 `Client` 接口。
2. `Agent` 在构造时持有 `Client`、`Backend`、`ToolManager` 引用。
3. `Agent.new()` 与 `Agent.load()` 创建 `Session`。
4. `Session.prompt()` 负责推进一轮对话，也就是延伸倒排链。
5. `Session` 在运行中通过 `Agent` 反向回调 `Client.update()`。

这样设计的原因是：

1. `Agent` 已经在构造时绑定了唯一的 `Client`，因此 `new()` 与 `load()` 无需再次传入 `client`。
2. 如果需要绑定不同的 frontend/client，应创建不同的 agent 实例。
3. 每个 agent 实例都是有状态的 stateful agent；其核心状态是它所管理的 sessions。

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
2. 白名单、访问者鉴权等逻辑属于 frontend 或 entry，不属于 agent 核心。
3. terminal、filesystem 等能力在本项目里优先建模为 tools，而不是 client 方法。

### 4.4 Agent 接口

```python
class Agent(Protocol):
    def __init__(self, client: Client, backend: Backend, tools: ToolManager) -> None: ...
    async def new(self, cwd: str | None = None) -> "Session": ...
    async def load(self, data: JSONValue) -> "Session": ...
```

语义映射：

1. `new()` 对应 ACP `session/new`
2. `load()` 对应 ACP `session/load`

说明：

1. `Agent` 在构造时完成依赖绑定。
2. `new()` 与 `load()` 不重复接收 `client` 参数。
3. 如需不同 client，应创建不同 agent 实例。

### 4.5 Session 接口

```python
class Session(Protocol):
    async def prompt(
        self,
        prompt: str | list[ContentBlock],
        *,
        allowed_tool_names: list[str] | None = None,
    ) -> PromptReturn: ...

    async def cancel(self) -> None: ...
    async def fork(self) -> "Session": ...
    def save(self) -> JSONValue: ...
```

语义映射：

1. `prompt()` 对应 ACP `session/prompt`
2. `cancel()` 对应 ACP `session/cancel`
3. `fork()` 与 `save()` 是项目扩展能力

说明：

1. `allowed_tool_names=None` 的语义固定为“本轮允许使用全部已注册 tools”。
2. `fork()` 不接收 `from_node_id`，避免把低频且复杂的节点选择暴露给调用方。
3. `fork()` 的语义就是基于当前 session 状态进行浅拷贝式分叉。
4. `save()` 导出当前 session 状态；`load()` 由 agent 负责恢复。

### 4.6 frontends 模块说明

`frontends` 是模块边界，不再单独定义一个稳定的 `Frontend` 协议。

原因：

1. 当前真正稳定的边界是 `Client`。
2. 各 frontend 只需要实现 `Client`，再各自提供自己的 `run(agent)` 入口即可。
3. `run(agent)` 不足以单独构成一个值得长期稳定的跨模块协议。

本期实现为 `CliClient`，其职责如下：

1. 由 `entry` 构造并注入 `agent`。
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
6. 当前只支持顶层 object + 一层平铺字段，不追求完整 JSON Schema。

额外约束：

1. tool 输入与输出都必须可 JSON 序列化。
2. 框架层通过 `json.dumps(...)` 校验可序列化性。
3. `session_id`、`cwd`、`call_id` 不进入 tool 函数签名；这些由 agent 内部管理。

### 5.3 ToolManager 接口

```python
class ToolManager(Protocol):
    def list(self) -> ToolMap: ...

    def invoke(
        self,
        name: str,
        **kwargs: JSONValue,
    ) -> JSONValue: ...
```

规则：

1. `list()` 返回当前 manager 聚合后的全部 tools。
2. agent 如需做“本轮仅允许部分 tools”，在 `list()` 返回结果上按名称筛选即可。
3. `allowed_tool_names=None` 的语义固定为“允许全部 tools”。
4. `invoke()` 的签名与底层 provider 一致，便于透传与测试。
5. `invoke()` 的返回值不限定为字符串，只要求可 JSON 序列化。
6. 未知 tool、参数不合法、执行失败都通过异常表示，不使用额外的错误码返回机制。
7. 建议内部至少区分两类异常：
   - `ToolInvokeError`：调用层错误，例如未知 tool、参数不合法
   - `ToolExecutionError`：tool 自身执行失败

### 5.4 tools 模块内部实现边界

`tools` 模块内部可以继续拆实现，但不向外暴露为一级模块接口：

1. builtin tool registry
2. config loader
3. MCP provider adapter
4. tool routing

对 `agent` 暴露的唯一稳定边界就是 `ToolManager`。

`tools` 模块内部注册对象的最小接口形态为：

```python
class ToolProvider(Protocol):
    def list(self) -> ToolMap: ...
    def invoke(self, name: str, **kwargs: JSONValue) -> JSONValue: ...
```

内置 tool 的最小函数形态为：

```python
def f(**kwargs: JSONValue) -> JSONValue:
    ...
```

说明：

1. provider 负责暴露一批 tools。
2. `ToolManager` 负责聚合多个 provider。
3. 由于 `ToolMap` 是字典结构，聚合时可以直接 `tools.update(provider.list())`。

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
4. 当前不要求 backend 支持流式 generator 接口；MVP 先使用普通 async 方法。
5. 如果后续实现 streaming，再把输入输出都调整为 generator 风格。

## 7. agent 模块内部数据结构

下面这些结构属于 `agent` 的内部实现，但需要先在设计文档里明确，因为它们决定了整个系统的行为。

### 7.1 倒排链节点

```python
@dataclass(slots=True)
class Node:
    id: str
    prev: "Node | None"
    created_at: datetime
    frozen: bool = False


@dataclass(slots=True)
class UserPromptNode(Node):
    kind: ClassVar[str] = "user_prompt"
    prompt: str | list[ContentBlock]


@dataclass(slots=True)
class AssistantResponseNode(Node):
    kind: ClassVar[str] = "assistant_response"
    text: str


@dataclass(slots=True)
class ToolCallNode(Node):
    kind: ClassVar[str] = "tool_call"
    calls: dict[str, dict[str, Any]]


@dataclass(slots=True)
class SummaryNode(Node):
    kind: ClassVar[str] = "summary"
    summary: JSONValue
```

规则：

1. 运行时通过 `prev` 对象引用回溯。
2. `id` 主要用于 save/load、日志、调试和 fork 入口。
3. 节点整体逻辑 append-only。
4. 只有当前 session 的未封口尾节点允许原地更新。
5. 可变节点在任意时刻只能被一个 session 作为活动尾节点持有。
6. 一旦节点被后继节点引用、被 fork 共享、当前 turn 结束或被取消，必须立刻冻结。

### 7.2 Session 对象状态

`Session` 本身就是状态对象，不再额外定义 `SessionState` 或 `ActiveTurn` 结构。

最小状态至少包括：

1. `id`
2. `cwd`
3. `tail`
4. 当前是否存在活跃 turn
5. 当前 turn 是否已请求取消
6. 本轮可见 tools 的上下文信息

### 7.3 Tool Call 节点约束

一次模型返回的一组并行 tool calls，落为一个 `ToolCallNode`。

建议 payload 结构：

```python
{
    "calls": {
        "call_xxx": {
            "tool_name": str,
            "arguments": dict[str, Any],
            "status": "pending" | "running" | "completed" | "failed" | "cancelled",
            "results": list[dict[str, Any]],
        },
    },
}
```

规则：

1. 一组并行 tool calls 属于同一个 `ToolCallNode`。
2. 节点内部用 `call_id` 区分多个 call。
3. 结果与状态更新依靠 `call_id` 对应，不依靠顺序。
4. 只要该节点还是当前尾节点，且未被其他 session 共享，就允许原地更新。
5. 若执行中被取消，该节点必须立刻标记为 `cancelled` 并冻结。
6. 冻结之后到达的迟到结果直接丢弃。

### 7.4 fork 规则

1. `session.fork()` 基于当前 session 状态创建一个新 session。
2. 新旧 session 共享已有历史节点。
3. fork 前如果当前尾节点仍可变，必须先冻结，再进行浅拷贝式分叉。
4. `fork()` 不暴露 `from_node_id` 参数。
5. 如果未来确实需要“从指定历史节点分叉”，再以新扩展方法加入。

### 7.5 压缩规则

当上下文接近窗口上限时：

1. 不修改旧链。
2. 不从旧链上摘节点。
3. 通过生成 `summary` 节点建立新链。
4. 当前 session 的尾指针指向新的压缩后链条。
5. 原始链保留，用于回放与 fork。

## 8. agent 的编排流程

`Session.prompt()` 的最小编排流程如下：

1. 校验当前 session 当前没有活跃 turn。
2. 标记当前 session 进入活跃 turn 状态。
3. 在当前尾部追加 `user_prompt` 节点。
4. 调用 `ToolManager.list()` 得到全部 tools；若 `allowed_tool_names is None`，则本轮允许全部 tools，否则按名称筛选。
5. 将本轮可见 tools 挂入当前 session 上下文，再调用 `Backend.generate(session)` 获取模型输出。
6. 若 backend 返回文本，则创建或更新尾部 `assistant_response`。
7. 若 backend 返回一组 tool calls，则追加一个 `tool_call` 节点。
8. agent 并发调用 `ToolManager.invoke(...)` 执行这些 tools。
9. tool 结果按 `call_id` 回写当前尾部 `tool_call` 节点，并通过 `Client.update(session, update)` 通知 frontend。
10. 所有 tool 结果准备好后，再次调用 `Backend.generate(session)`。
11. 若过程中收到 cancel，则停止继续推进，冻结最后一个未封口节点，并返回 `("cancelled", partial_output)`。
12. 正常结束时返回 `("end_turn", output_text)`。
13. 若发生真正失败，则直接抛异常，而不是返回 `failed`。
14. 清理当前 session 的活跃 turn 状态。

`Session.cancel()` 的规则：

1. 如果 session 没有活跃 turn，直接返回。
2. 如果有活跃 turn，只设置“已请求取消”标记。
3. 真正的停止、冻结与收尾由 `prompt()` 所在协程完成。

## 9. entry 模块接口

`entry` 是最后的封装层，用于把分散模块装配成可运行程序。

### 9.1 入口职责

1. 加载 config。
2. 初始化 logger。
3. 初始化 `ToolManager`。
4. 初始化 `Backend`。
5. 初始化 `Agent`。
6. 初始化具体 client/frontend 实现。
7. 将它们按依赖关系拼装起来。
8. 推动具体 client 的 `run(agent)` 执行。

### 9.2 Entry 接口

```python
class EntryPoint(Protocol):
    async def run(self) -> None: ...
```

本期可以有一个默认实现，例如：

```python
class DefaultEntryPoint:
    async def run(self) -> None: ...
```

`entry` 层不承载业务逻辑；它只是装配器。

## 10. 测试设计

测试设计需要和模块边界一起确定，因为这直接影响后续开发方式。

### 10.1 测试原则

1. 各模块在封装完成前应保持分散，方便单测。
2. 模块边界必须足够稳定，才能用 mock 替代真实依赖。
3. 测试不仅用于验收，也用于反推 backend 与模型实际需要的行为。

### 10.2 必须提供的 mock 实现

为了程序化自动化测试，至少需要以下 mock：

1. `MockFrontend`
   - 实现 `Client` 接口。
   - 程序化创建 session、发送 prompt。
   - 收集 `SessionUpdate` 与 `PromptResult`。
   - 不依赖终端交互。
2. `MockToolManager`
   - 返回固定 `ToolMap`。
   - 按预设规则返回 JSON 可序列化结果。
   - 支持模拟成功、失败、延迟、取消后迟到结果。
3. `MockBackend`
   - 根据预设脚本返回文本或 tool calls。
   - 支持模拟多轮 tool use。
   - 支持模拟取消和失败。

### 10.3 测试分层

建议至少有三层测试：

1. 模块单元测试
   - `agent` 内部倒排链、freeze、fork、cancel 规则
   - `tools` 的 list/call/filter 行为
   - `backends` 的请求转换逻辑
2. 协议边界测试
   - frontend-agent-session 的 ACP 类接口行为
   - agent-tools 的 MCP 类接口行为
3. 集成测试
   - `MockFrontend + Agent + MockToolManager + MockBackend`
   - `CliClient + Agent + MockToolManager + MockBackend`

### 10.4 第一批关键用例

第一批必须覆盖：

1. 无 tool 的单轮对话。
2. 一轮中单个 tool call。
3. 一轮中多个并行 tool calls。
4. tool call 进行中触发 cancel。
5. cancel 后迟到 tool result 被丢弃。
6. 从当前 session fork 出新 session。
7. 仅允许部分 tools 时，agent 只能看到指定子集。
8. backend 连续两轮请求：先请求 tools，再基于 tool result 输出最终文本。

## 11. 当前结论

当前准备按以下结构推进实现：

1. 一级模块固定为 `agent`、`tools`、`frontends`、`backends`、`entry`
2. `frontends <-> agent` 用 ACP 类接口
3. `tools <-> agent` 用 MCP 类接口
4. `backends <-> agent` 先使用最小内部接口
5. `entry` 只负责装配，不承载业务逻辑
6. `Client` 是稳定边界，`frontends` 不再单独定义额外协议
7. 测试中必须提供 mock 版 frontend/client、tools、backend

如果这版接口和边界确认无误，下一步再进入代码实现。
