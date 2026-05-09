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
        "thinking_chunk",
        "tool_call",
        "tool_call_update",
    ]
    data: dict[str, JSONValue]
```

说明：

1. `SessionUpdate` 是 client/frontend 观察到的事件。
2. `agent_message_chunk` 是模型最终输出的显示内容；`thinking_chunk` 是模型的思考过程（如 reasoning）。CLI 中两者分离输出，显示内容直接打印，思考内容可折叠或前缀标注。
3. 每条消息在输出前 strip 前后空白字符。
4. `request_permission()` 已启用：权限系统已实现，CLI/ACP/Web 三端均接入真实的权限确认流程。
5. `prompt()` 失败时不返回 `failed`，而是直接抛异常，遵循 Python 风格。

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
4. `request_permission()`应在 DEBUG 级别记录 `kind` 和 `payload`，便于审计和调试。

### 4.4 Agent 接口

```python
class Agent(Protocol):
    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolProvider,
        compressor: "Compressor | None" = None,
        permissions: "PermissionManager | None" = None,
        memory: "Memory | None" = None,
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
5. `permissions` 为可选注入；注入时每个 tool 调用前检查权限规则（allow/deny/ask）。
6. `memory` 为可选注入；注入时每轮 `_run_turn` 开始前 `recall()` 注入记忆，结束后 `remember()` 更新记忆。
7. `tools` 参数类型为 `ToolProvider`。Agent 运行时只关心"能列出工具、能调用工具"，不关心对方是单个 provider 还是聚合后的 `ToolManager`。
8. backends支持多个，agent只持有一个backend，即名字为primary的那个。compressor在构造的时候，会根据配置，决定使用同一个backend，还是获得另一个。

### 4.5 Session 接口

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

语义映射：

1. `prompt()` 对应 ACP `session/prompt`
2. `cancel()` 对应 ACP `session/cancel`
3. `fork()`、`compress()`、`save()` 是项目扩展能力

说明：

1. `allowed_tools=None` 表示使用全部已注册 tool，向后兼容；传入列表时，本轮 backend 仅可见该子集，不在列表中的 tool 完全不出现在 tools 定义中。
2. `SessionCore` 内部在 `_run_turn` 开始时将 `allowed_tools` 存入 `_turn_allowed_tools`，并通过 `get_turn_tool_map()` 方法返回过滤后的 `ToolMap`；backend 读取 `session.get_turn_tool_map()` 而非 `session.agent.tools.list()`。
3. backend 返回的 `tool_calls` 若包含不在允许列表中的 tool，视为非法调用：以 `ToolInvokeError` 记录到 `ToolResultNode.results`（`status="failed"`，`content` 为"Tool not in allowed list"），不实际执行该 tool。
4. `fork()` 不接收 `from_node_id`，避免把低频且复杂的节点选择暴露给调用方。
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
6. 处理 `/list-tools` 命令：列出当前 agent 已注册的所有 tools。
7. readline 集成：支持方向键召回历史、指令历史持久化到 `~/.little_agent_history`、Tab 补全 `/` 命令。

### 4.7 CLI 显示设计

1. 消息分离：`agent_message_chunk` 前缀加 `[Agent]`；`thinking_chunk` 前缀标注为 `[Thinking]` 或折叠显示。两者输出区域分离，避免混淆。
2. 空白处理：所有消息输出前 `strip()` 去除前后空白。
3. Tool call 参数显示：`tool_call` 类型更新除显示 tool 名称外，还显示具体调用参数（arguments）。若参数文本超过 3 行，截断尾部并显示 `...{n} lines...`。

### 4.8 CLI 命令清单

| 命令 | 作用 |
| --- | --- |
| `/quit` | 退出 CLI |
| `/exit` | `/quit` 的别名，行为完全一致 |
| `/cancel` | 取消当前活跃 turn |
| `/fork` | 从当前 session 分叉出新 session |
| `/new` | 创建全新 session |
| `/save <path>` | 保存当前 session 到文件 |
| `/load <path>` | 从文件加载 session |
| `/list-tools` | 列出当前已注册的所有 tool 名称与描述 |

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

快速分发约定（可选）

`ToolManager.invoke()` 在调用 `provider.invoke()` 前，会先检查 provider 是否存在与 tool 同名的方法：

- 若存在且可调用，直接调用该方法，跳过 `provider.invoke()` 的分发层。
- `list` 和 `invoke` 这两个名称被保留，永远不走快速路径（避免与 Protocol 方法冲突）。
- 这是一条**约定**，不修改 `ToolProvider` Protocol 接口，provider 无需实现任何额外接口。

快速路径方法的签名约定：

```python
async def <tool_name>(self, **kwargs: JSONValue) -> JSONValue:
    ...
```

优先为每个 tool 定义对应方法，`invoke()` 只做兜底分发（处理动态注册的 tool 或不想显式定义方法的场景）。

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

### 5.6 内置 Bash Tool

系统内置一个 `bash` tool，允许 Agent 执行 shell 命令。

**Tool 定义：**

- name: `bash`
- description: `Execute a shell command and return stdout/stderr`
- 参数：
  - `command` (string, required): 要执行的 shell 命令
  - `cwd` (string, optional): 工作目录
  - `env` (object, optional): 环境变量键值对
  - `stdin` (string, optional): 标准输入内容

**实现要点：**

1. 使用 `asyncio.create_subprocess_shell` 异步执行命令。
2. 捕获 stdout 和 stderr，返回合并后的字符串输出。
3. 命令超时时间默认 30 秒，超时后 kill 进程并返回超时信息。
4. 命令执行失败（非零退出码）返回 stderr 内容，不抛异常（让模型自行判断）。
5. `cwd`、`env`、`stdin` 通过 `create_subprocess_shell` 和 `communicate()` 传入。
6. 不传入新参数时行为不变（向后兼容）。

**注册方式：**

启动脚本先加载配置文件中的 `tools.providers` 列表，然后将 `BashToolProvider` append 到列表末尾，最后统一调用 `ToolManager.register()` 注册所有 providers。内置 tool 不通过特殊机制注册，与普通配置加载的 provider 走同一流程。

### 5.7 Task Tool

系统内置一个 `task` tool，允许 Agent 创建子任务（子会话），独立执行并返回结果。

Tool 定义：

- name: `create_task`
- description: `Create a sub-task with its own session and execute it`
- 参数：
  - `prompt` (string, required): 子任务的提示词
  - `id` (int, optional): 子任务的id
  - `depends` (array of int, optional): 子任务的依赖
  - `tools` (array of string, optional): 子任务可用的 tool 名称列表（默认可用全部）
  - `inheritance` (bool, optional): 继承发起task的chain，sub-task的AI能看到之前全部对话历史

实现要点：

1. 子任务有独立的 `Session`，与主会话隔离。
2. 子任务执行完成后，结果（`output_text` 和 `stop_reason`）返回给主会话。
3. 子任务异常不影响主会话（异常被捕获并作为 failed 结果返回）。
4. inheritance默认为false。如果inheritance为true，那么从当前session上倒推到第一个没有frozen属性的node，做fork，加UserPromptNode节点，然后执行任务。一般不从当前fork，因为当前一般是ToolResultNode，还要继续写入。
5. 发起子任务后，tool call就不会超时。但是每个task都有300s的超时时间。
6. 子任务的tools里面，去掉task tool，避免递归调用。

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
    usage: dict[str, int] | None = None  # e.g. {"input_tokens": 100, "output_tokens": 50}
    thinking_text: str | None = None     # accumulated reasoning text (if model supports it)
```

### 6.3 Backend 接口

```python
from typing import AsyncIterator

class Backend(Protocol):
    def generate(self, session: "Session") -> AsyncIterator[SessionUpdate | BackendTurnResult]: ...
```

说明：

1. `generate()` 返回一个 `AsyncIterator`，先 yield 零到多个 `SessionUpdate`（类型为 `agent_message_chunk` 或 `thinking_chunk`），最后 yield 一个 `BackendTurnResult` 作为终止标记。
2. 消费方（`AgentCore._run_turn`）遍历 iterator：遇到 `SessionUpdate` 时立即 `client.update()` 转发；遇到 `BackendTurnResult` 时退出循环，处理 `finish_reason`。
3. backend 接收 `session` 对象，负责读取 session 的链式历史并转换为真实后端的输入，同时把 session 当前可见的 tools 转换为 OpenAI 需要的工具定义。
4. `OpenAIBackend` 使用流式 API（`stream=True`），逐 chunk yield `agent_message_chunk` / `thinking_chunk` 更新，在流结束后 yield 最终的 `BackendTurnResult`。
5. 性能计数：在 `BackendTurnResult` yield 前记录 INFO 级别日志，包括 input/output token 数、执行时间、缓存信息（如 `cached_tokens`）。
6. DEBUG 日志：请求开始前记录完整 payload（messages、tools 等）。
7. 超时控制：streaming 模式下对整个流设置超时，超时后关闭 stream 并抛出 `BackendTimeoutError`，由上层处理。
8. context-overflow 异常：当底层 API 返回上下文长度超限错误（如 OpenAI 的 `context_length_exceeded`、HTTP 400 含 `maximum context length` 等模式）时，backend 必须识别并抛出 `ContextOverflowError`（定义在 `backends/exceptions.py`）。其他 `BadRequestError` 原样向上抛。该异常由 agent core 按 §7.6.6 in-turn retry 路径处理。
9. `BackendTurnResult.thinking_text` 保留字段（用于非流式 fallback 或测试），流式模式下通常为 `None`（thinking 内容已通过 `thinking_chunk` 逐 chunk 发出）。
10. `<think>` 标签处理：部分模型（如 DeepSeek-R1）不使用 `reasoning_content` 字段，而是在 `content` 中以 `<think>...</think>` 标签包裹思考内容。`OpenAIBackend` 在 streaming 过程中维护一个状态机，将标签前的内容作为 `agent_message_chunk` 立刻 emit，标签内的内容作为 `thinking_chunk` 逐 chunk emit，标签后恢复 `agent_message_chunk`。维护最多 8 字节的 lookahead buffer 处理跨 chunk 的标签截断；流结束时 flush 残余 buffer（未闭合的 `<think>` 按 `thinking_chunk` 处理）。`reasoning_content` 路径不受影响。

### 6.4 并发控制

并发限制是 backend 自身的关注点，不由调用方（agent / compressor）控制。原因：rate limit 与 API key 共享在同一个 backend 实例上，多个 session、compressor 调用、未来其他用法都共用此约束；只有 backend 层有完整视图。

规则：

1. 每个 `Backend` 实例在构造时根据配置项 `max_concurrency` 初始化一把 `asyncio.Semaphore`；默认 `1`，表示串行。
2. 所有 `generate()` 调用必须在内部 acquire 该 semaphore，调用完成（无论成功、异常、取消）后 release。
3. 调用方可以放心地并发发起 `generate()`（如 `asyncio.gather`），实际并发由 backend 的 semaphore gate。
4. Semaphore 的获取 / 释放对调用方透明；不暴露在接口签名上。
5. 设计上保留并发能力，未来调整并发只需改配置，不需要改业务代码。

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

压缩能力以可插拔协议定义：

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
6. compressor在构造的时候，根据配置，main.py决定compressor和agent使用同一个backend，还是获得另一个。当backends里面有一个叫compressor的backend的时候，使用那个。如果没有，和agent使用同一个。
7. agent 编排在每次 turn 结束后自动评估并按需调度 `compress()`，触发策略详见 §7.6。

### 7.6 自动压缩触发策略

`Compressor.compress()` 由 agent 在每次 turn 完成后自动触发，frontend 不感知。post-turn 触发让用户阅读 AI 输出与键入下一条消息的同时，agent 在后台压缩历史，避免把压缩延迟塞入用户等待回复的路径。

#### 7.6.1 触发时机

post-turn：每次 `Session.prompt()` 即将返回前（成功、取消、异常都参与判定）评估 §7.6.2 判据。命中则 agent 异步调度 compress 任务（`asyncio.create_task`），prompt() 立即返回 `(stop_reason, output)` 给 frontend，不等待压缩完成。

compress 任务运行期间复用 session 的活跃 turn 标记（与正常 turn 互斥）。新到达的 prompt 通过 §8 既有的 pending 队列机制等待，与活跃 turn 处理逻辑一致；compress 结束后释放标记，pending 唤醒。

#### 7.6.2 触发判据

满足以下任一条件即调度自动压缩：

1. **token 阈值（首选）**：本 turn 最后一次 backend 调用的 `BackendTurnResult.usage.input_tokens + usage.output_tokens` 与该 backend 配置的 `context_window` 相比，比值大于 `R`。`R` 由 agent 配置项 `R` 调整，默认 `0.5`，取值范围 (0, 1]。
2. **字符兜底**：本 turn 没有有效 usage 数据（usage 为 None 或字段为 0），退化到字符数估算：从 tail 往前累加每个节点序列化后的字符数，除以 4 得到 token 估算值，同样比较 `R` 阈值。
3. **context-overflow 错误兜底**：见 §7.6.6。该路径不属于 post-turn，而是在 turn 内同步触发并 retry。

#### 7.6.3 保留窗口

最近 `K` 个 turn 不参与压缩。`K` 由 compressor 配置项 `keep_turns` 调整，默认 `5`，下限 `3`（配置低于 3 时报警并强制使用 3）。

turn 边界：从一条 `UserPromptNode` 起，到下一条 `UserPromptNode` 之前的所有节点（含 ToolCallNode / ToolResultNode / AssistantResponseNode）属于同一个 turn。

#### 7.6.4 压缩算法

1. **压缩区上界**：从 tail 往前回溯，找到最后一条 `SummaryNode` 即为上界（再往前皆为已压缩内容，本次不重复处理）；若链上无 SummaryNode，上界为链首。
2. **保留区**：tail 起最近 `K` 个 turn 的所有节点。
3. **被压区**：上界与保留区之间的所有节点，按 turn 切分。
4. **压缩**：每个被压 turn 一次 LLM 调用，压成一条 `SummaryNode`，保留关键事实、决策和上下文（"相对详细"，非极致压缩）。多个被压 turn 通过 `asyncio.gather` 并发发起调用，实际并发由 backend 层的 `max_concurrency` 限制（详见 §6.4）；按时序串接结果。任一并发请求失败按 §7.6.6 处理（all-or-nothing：丢弃整批，旧链保留）。
5. **新链拼装**：上界之前的旧 SummaryNode + 本次新产出的 SummaryNode + 保留区。
6. 压缩失败处理见 §7.6.6。

#### 7.6.5 历史上限

压缩历史也有窗口限制，避免 SummaryNode 累积无限制：

1. 上限 `W = compressed_window * context_window`（tokens）。`compressed_window` 是 compressor 配置项，单位为比例（取值范围 (0, 1)），默认 `0.2`；`context_window` 取自 primary backend 配置。
2. 计量：SummaryNode 没有 usage 数据，统一用字符数 / 4 估算。
3. 时机：压缩算法（§7.6.4）拼装新链后立刻执行。
4. 算法：从最新 SummaryNode 往旧累加估算 token；累加值首次超过 `W` 时，该位置之前的所有 SummaryNode 整体丢弃，与 SummaryNode 边界对齐，不切断单条 SummaryNode。

#### 7.6.6 失败处理

`Compressor.compress()` 抛出异常（含 context-overflow、超时、其他 backend 异常）时：

1. **post-turn 路径**：异常向 frontend 抛，frontend 显示错误；session 链结构不破坏（旧 SummaryNode 与保留区保持原样）。处理方式与普通 backend 调用失败一致。
2. **in-turn overflow retry 路径**：在 §8 主循环中 backend 抛 context-overflow 错误时，agent 同步调用 `compressor.compress(self.tail)` 一次，把返回值赋给 `self.tail`，然后对当前 backend 调用 retry 一次。retry 仍 overflow 则按普通 backend 异常向上抛，turn 终止。该路径不通知 frontend，因为反馈出去会让用户介入并续写 prompt，导致历史链增长，与压缩目的相反；agent 自行控制 retry。

#### 7.6.7 日志

每次自动压缩必须输出 INFO 级别日志，至少包含：

- 触发判据：`token_threshold` / `char_fallback` / `overflow_retry`
- 触发值：估算 token 数与对应 `context_window`
- 被压 turn 数与新生成 SummaryNode 数
- 历史上限触发的丢弃 SummaryNode 数（若有）
- 压缩耗时（毫秒）

#### 7.6.8 backend 配置

每个 backend 配置增加 `context_window` 字段（int，默认 `128000`）。当前主流模型的 context window 无法从 API 读取，统一由配置指定。agent 在 §7.6.2 触发判据中读取本次 backend 调用对应 backend 的 `context_window`。

## 8. agent 的编排流程

`Session.prompt()` 的编排流程如下：

1. 若当前 session 已有活跃 turn：进入 pending 队列；队列满则抛 `SessionBusy`。否则立刻占据，标记"有活跃 turn"。
2. 在当前尾部追加 `UserPromptNode`，旧尾若为可变类型先冻结。
3. 进入主循环（循环上限 `MAX_TURN_ITERATIONS`，默认 20）：
   1. 调用 `session.get_turn_tool_map()` 得到本轮可见 tool 子集（若 `allowed_tools` 为 None，则返回全部已注册 tool）。调用 `Backend.generate(session)` 得到 async iterator；backend 内部读取 `session.get_turn_tool_map()` 而非 `session.agent.tools.list()`；遍历其产出：
      - 遇到 `SessionUpdate`（`agent_message_chunk` / `thinking_chunk`）：立即通过 `client.update()` 转发给 frontend，实现逐 token 流式显示。
      - 遇到 `BackendTurnResult`：保存为 `result`，退出遍历循环。
      - 若 backend 抛 context-overflow 错误：进入 §7.6.6 中的 in-turn retry 路径（同步调用 `compressor.compress(self.tail)` 一次，更新 `self.tail`，对本次 `Backend.generate(session)` retry 一次）。retry 仍 overflow 按普通 backend 异常处理，turn 终止。该 retry 不经 frontend 通知。
   2. 若 `result.finish_reason == "completed"`：
      - 追加 `AssistantResponseNode`（内容来自 `result.output_text`），冻结。
      - 跳出主循环，返回 `("end_turn", output_text)`。
   3. 若 `finish_reason == "tool_call"`：
      - 追加 `ToolCallNode`（冻结）。
      - 通过 `Client.update(session, tool_call)` 通知 frontend。
      - 追加 `ToolResultNode`（可变）。
      - 并发调用 `ToolProvider.invoke(...)` 执行全部 tools（`asyncio.gather`）。调用前先检查 tool name 是否在本轮允许列表内；不在列表中的 tool call 直接记录为失败（`status="failed"`，`content="Tool not in allowed list"`），不实际调用。
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
7. 无论成功、取消还是异常，finally 阶段先按 §7.6.2 判据评估是否触发 post-turn 自动压缩：
   - 触发：保持活跃 turn 标记不释放，异步调度 compress 任务（`asyncio.create_task`），由该任务在结束时释放活跃 turn 标记；pending 队列在 compress 结束后才唤醒。
   - 未触发：立即清理活跃 turn 标记；pending 队列非空时唤醒下一个排队协程继续处理。
   失败不得污染队列。
8. `Session.cancel()` 只影响当前活跃 turn（含 post-turn compress 任务），不清空 pending 队列。

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

1. 解析 CLI 参数（包括 `--loglevel` 等日志级别 flag）。
2. 加载 YAML 配置文件。
3. 初始化 logger：
   - 若配置中存在 `cfg['logging']`，使用 `logging.config.dictConfig(cfg['logging'])` 加载完整日志配置。
   - 若不存在，使用内置 `_DEFAULT_LOGGING_CONFIG` 标准化 dictConfig。
   - `--loglevel` 参数强制覆盖 `cfg['logging']['loggers']['']['level']`。
4. 初始化 `ToolManager`：构造 `ToolManager` 具体实例；加载配置中的 providers 列表，将 `BashToolProvider` append 到列表末尾，然后统一注册所有 providers。
5. 初始化 `Backend`（包括 base_url，默认为 None，使用 OpenAI 默认地址）。
6. 多 backend 初始化：若配置中存在多个 backend 定义，按名称构造多个 `Backend` 实例。
7. 初始化 `Compressor`（可选）。
8. 初始化具体 `Client` 实现（本期为 `CliClient`）。
9. 用上述依赖构造 `Agent`。
10. 调用 client 的 `run(agent)` 启动交互。

不承载业务逻辑。

### 9.2 配置文件 schema

本期使用 YAML。最小 schema（实现时可按需扩展）：

```yaml
# 多 backend 配置，无需考虑向后兼容
backends:
  primary:
    type: openai
    model: gpt-4
    api_key: OPENAI_API_KEY
    base_url: https://api.openai.com/v1  # optional
    context_window: 128000               # optional, default 128000；§7.6.8
    max_concurrency: 1                   # optional, default 1；§6.4
  compressor:
    type: openai
    model: gpt-3.5-turbo
    api_key_env: OPENAI_API_KEY_NAME_IN_ENV
    context_window: 128000
    max_concurrency: 1

# 自动压缩触发阈值，§7.6.2
agent:
  R: 0.5                                 # post-turn 触发阈值，取值范围 (0, 1]，默认 0.5

# 压缩策略参数，§7.6.3 / §7.6.5
compressor:
  keep_turns: 5                          # 不参与压缩的最近 turn 数，下限 3，默认 5
  compressed_window: 0.2                 # 压缩历史上限比例，W = compressed_window * primary.context_window，默认 0.2

tools:
  providers:
    - type: python
      module: my_tools.weather
    - type: python
      module: my_tools.calculator

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
2. 不对并行 tool 调用设并发上限。未来可能加入。
3. `save()`/`load()` 的详细 schema 本期不定；只确定需要序列化节点链表，其他字段随实现确定。

## 12. 当前结论

当前准备按以下结构推进实现：

1. 一级模块固定为 `agent`、`tools`、`frontends`、`backends`
2. 启动装配由 `little-agent` 命令行脚本完成（`pyproject.toml` 的 `[project.scripts]` 注册）
3. `frontends <-> agent` 用 ACP 类接口；`Client` 是稳定边界
4. `tools <-> agent` 用 MCP 类接口；`ToolProvider` 是稳定边界
5. `backends <-> agent` 先使用最小内部接口
6. 测试中提供 `MockClient`、`MockToolProvider`、`MockBackend`、`MockAgent`
