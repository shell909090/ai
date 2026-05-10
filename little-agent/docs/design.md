# 设计文档

## 1. 概述

### 1.1 目标

最小可运行 Agent 系统：对话 + tools。

- 内核 `asyncio`。
- 与 ACP 等效语义，同进程内不机械复制 JSON-RPC 包装。
- 三个 frontend：`cli`、`web`、`acp`。
- tool 通过配置文件注册，描述对齐 MCP。
- 对话历史用倒排链；运行时通过对象引用回溯。

### 1.2 模块划分

四个一级模块：`agent`、`tools`、`frontends`、`backends`。`session` / `chain` / `persistence` 是 `agent` 内部实现。启动脚本 `little-agent` 是装配层。

### 1.3 依赖方向

```
little-agent (script) → frontends → agent → {tools, backends}
```

约束：

1. `agent` 不依赖具体 frontend / backend / tool 实现。
2. 启动脚本把具体实现注入到协议接口上。
3. `frontends ↔ agent` 稳定边界是 `Client`（§4）。
4. `tools ↔ agent` 稳定边界是 `ToolRegistry`（§3）。
5. `backends ↔ agent` 走项目内部接口（§5）。

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
    output_text: str                    # tool call 前的 reasoning/说明，可为空
    calls: dict[str, dict[str, Any]]    # call_id -> {tool_name, arguments}


@dataclass(slots=True)
class ToolResultNode(Node):
    kind: ClassVar[str] = "tool_result"
    results: dict[str, dict[str, Any]]  # call_id -> {status, content}
    frozen: bool = False


@dataclass(slots=True)
class SummaryNode(Node):
    kind: ClassVar[str] = "summary"
    summary: str
```

规则：

1. 运行时通过 `prev` 对象引用回溯。`id` 用于 save/load、日志、调试、fork 入口、SessionLogger 状态跟踪。
2. 节点整体逻辑 append-only。
3. `frozen` 字段只出现在写入过程中可变的节点：`AssistantResponseNode`、`ToolResultNode`。其他节点创建即不可变。
4. 可变节点在任意时刻只能被一个 session 作为活跃尾节点持有。
5. 触发冻结的时机（由 session 管理）：
   - 追加新节点时旧尾若可变，立刻冻结。
   - session 被 fork 时当前尾若可变，立刻冻结。
   - 当前 turn 结束或被取消时，尾节点立刻冻结。

### 2.2 Session 状态

`Session` 本身就是状态对象。最小状态：

1. `id`
2. `cwd`
3. `tail`（当前链尾）
4. 是否存在活跃 turn
5. 当前 turn 是否已请求取消
6. pending prompt 队列（容量 3，满则抛 `SessionBusyError`）

并发规则：

1. 非 fork 产生的 session 持有完全独立的链条。
2. fork 产生的新 session 在 fork 点之前共享已冻结的历史节点，之后各自追加。
3. 任何时刻，同一可变节点只能被一个 session 作为活跃尾节点持有。

### 2.3 Tool Call 与 Tool Result 节点约束

一组并行 tool calls 落为一个 `ToolCallNode`，紧接一个 `ToolResultNode` 承载结果。

`ToolCallNode.calls`：

```python
{"call_xxx": {"tool_name": str, "arguments": dict[str, Any]}}
```

`ToolResultNode.results`：

```python
{"call_xxx": {"status": "completed" | "failed" | "cancelled", "content": JSONValue}}
```

规则：

1. `ToolCallNode` 由 backend 一次写入后立刻冻结。
2. `ToolResultNode` 跟随其后创建，按 `call_id` 逐步回填。
3. 结果与状态依靠 `call_id` 对应，不依靠顺序。
4. tool 执行抛出的异常由编排层 `except Exception` 捕获，写入 `status="failed"`，`content` 为异常信息。**异常不冒出 prompt turn**。
5. 取消时未完成的 call 标记 `cancelled`，节点冻结，迟到结果丢弃。

### 2.4 fork 规则

1. `session.fork()` 基于当前 session 状态创建新 session，共享已有历史节点。
2. fork 前若当前尾可变，必须先冻结。
3. 存在活跃 turn 时调用 fork 直接抛异常。
4. 不暴露 `from_node_id`；如需"从指定节点分叉"以新方法加入。

### 2.5 编排流程

`Session.prompt()` 流程：

1. 已有活跃 turn：进入 pending 队列，满则抛 `SessionBusyError`；否则占据。
2. 追加 `UserPromptNode`，旧尾若可变先冻结。
3. 主循环（上限 `MAX_TURN_ITERATIONS=20`）：
   1. 调用 `Backend.generate(session)` 得到 async iterator。遍历产出：`SessionUpdate` 通过 `client.update()` 转发；`BackendTurnResult` 保存为 `result` 退出遍历；context-overflow 错误进入 §2.6.4 in-turn retry。
   2. `finish_reason == "completed"`：追加 `AssistantResponseNode`（冻结），返回 `("end_turn", output_text)`。
   3. `finish_reason == "tool_call"`：
      - `result.output_text` 非空时存入 `ToolCallNode.output_text`。
      - 追加 `ToolCallNode`（冻结），通过 `Client.update` 通知 frontend。
      - 追加 `ToolResultNode`（可变）。
      - 检查每个 tool name 是否在 `allowed_tools` 内；不在则记 `failed`，不调用。
      - 通过 permission chain 检查；deny 则记 `failed`，不调用。
      - 并发执行允许的 tools（`asyncio.gather`），按 §2.3 写入。
      - 每个结果就位通过 `Client.update(tool_call_update)` 通知。
      - 全部结果到位或 turn 取消后，`ToolResultNode` 冻结。
4. 超过 `MAX_TURN_ITERATIONS` 抛异常。
5. 收到 cancel：等当前 backend 调用结束，未完成 tool call 标 `cancelled`，节点冻结，返回 `("cancelled", partial_output)`。
6. 真正失败（backend 异常等）直接抛异常，不返回 `failed`。
7. finally 阶段：
   1. 若已注入 `loggers`，依次调用 `logger.log(session)`（详见 §2.9）。
   2. 若已注入 `memory`，调用 `memory.remember(session)`。
   3. 按 §2.6.2 评估是否触发 post-turn 自动压缩：
      - 触发：保留活跃 turn 标记，异步调度 compress 任务（`asyncio.create_task`），由该任务在结束时释放标记并唤醒 pending 队列。
      - 未触发：清理活跃 turn 标记；pending 队列非空则唤醒下一个。

`Session.cancel()`：无活跃 turn 直接返回；否则只设"已请求取消"标记，停止/冻结/收尾由 `prompt()` 协程完成；cancel 也作用于 post-turn compress 任务。

### 2.6 压缩

#### 2.6.1 Compressor 协议

```python
class Compressor(Protocol):
    async def compress(self, head: Node) -> Node: ...
```

规则：

1. 输入：链头节点（含通过 `prev` 可达的全部历史）。
2. 输出：新链头节点（通常为 `SummaryNode`，协议不强制）。
3. 由启动脚本按配置构造，在 `Agent.__init__` 注入。
4. 配置中存在名为 `compressor` 的 backend 时使用它，否则与 agent 共用 backend。
5. `Session.compress()`：未注入 compressor 或存在活跃 turn 抛异常；否则调用 `compressor.compress(tail)` 并把返回设为新 tail。
6. 旧链不修改，不从旧链摘节点（保护 fork session 的链完整性）。
7. agent 编排在每次 turn 结束后自动评估并按需调度，详见 §2.6.2。

#### 2.6.2 自动触发策略

每次 `Session.prompt()` 即将返回前评估判据。命中则异步调度 compress 任务。

判据（任一即触发）：

1. **token 阈值（首选）**：本 turn 最后一次 backend 调用的 `usage.input_tokens + usage.output_tokens` 与该 backend 的 `context_window` 之比超过 `R`。`R` 由 agent 配置项 `R` 调整，默认 `0.75`，取值 (0, 1]。
2. **字符兜底**：本 turn 无有效 usage，从 tail 累加节点序列化字节数（UTF-8）除以 3 估算 token，比较 `R`。
3. **context-overflow 兜底**：见 §2.6.4。

#### 2.6.3 算法

参数：`keep_turns`（保留窗口，默认 3，下限 1），`compressed_window`（压缩历史上限比例，默认 0.15）。`W = compressed_window * primary.context_window`（tokens）。

turn 边界：从一条 `UserPromptNode` 起，到下一条 `UserPromptNode` 之前的所有节点。

算法：

1. **压缩区上界**：从 tail 往前回溯，找到最后一条 `SummaryNode`；若无则上界为链首。
2. **保留区**：tail 起最近 `keep_turns` 个 turn。
3. **被压区**：上界与保留区之间，按 turn 切分。
4. **压缩**：每个被压 turn 一次 LLM 调用，压成一条 `SummaryNode`。多 turn 通过 `asyncio.gather` 并发；任一失败按 all-or-nothing 丢弃整批。
5. **新链拼装**：上界之前的旧 SummaryNode + 新产出 SummaryNode + 保留区。保留区节点用 `dataclasses.replace` 复制以避免修改 fork 共享的旧链。
6. **W 上限**：从最新 SummaryNode 往旧累加估算 token（UTF-8 字节数 / 3），超 `W` 处对齐边界丢弃更早的 SummaryNode；至少保留 1 条。

#### 2.6.4 失败处理

- **post-turn 路径**：异常向 frontend 抛，session 链不破坏。
- **in-turn overflow retry**：主循环中 backend 抛 `ContextOverflowError` 时，agent 同步调用 `compressor.compress(self.tail)` 一次，retry 当前 backend 调用一次；retry 仍 overflow 按普通异常上抛。

#### 2.6.5 日志

每次自动压缩输出 INFO：触发判据、估算 token、被压 turn 数、新生成 SummaryNode 数、丢弃数、耗时。

### 2.7 Permissions

权限系统采用 Chain of Responsibility。

```python
class PermissionChecker(Protocol):
    async def request_permission(
        self, session: Session, kind: str, payload: dict[str, JSONValue]
    ) -> bool: ...
```

`Client` 满足该 Protocol，作为 chain 末端（向用户询问）。

`Agent.permissions: PermissionChecker` 始终非 None；未配置时默认为 `client`，每次询问用户。

chain 从配置 list 尾部往头部构建；请求从头部向尾部流转，第一个能决策的 checker 截断 chain。

内置 checker：

- **YesManChecker**：`type: yesman`，无配置项，始终返回 True。
- **BlackWhiteListChecker**：`type: blackwhitelist`，`blacklist` / `whitelist` 为 fnmatch 模式列表；blacklist 优先于 whitelist；都不命中传给 `next`。

调用方式：每个 tool call 一次

```python
allowed = await session.agent.permissions.request_permission(
    session, tc.tool_name, {"arguments": tc.arguments}
)
```

返回 False 时记 `failed`，content `"Permission denied"`，不执行。`allowed_tools`（turn 级别）作为独立前置检查，不经过 chain。

### 2.8 Memory

可选注入子系统：

```python
class Memory(Protocol):
    async def recall(self) -> str: ...
    async def remember(self, session: Session) -> None: ...
```

规则：

1. 由启动脚本按配置构造，在 `Agent.__init__` 注入。
2. 注入时每轮 `_run_turn` 开始前调用 `recall()`，返回文本作为 `SummaryNode` 注入到 session tail。
3. 每轮结束后（含取消、异常）调用 `remember(session)`。
4. 未注入则跳过。

### 2.9 SessionLogger

会话日志系统，记录"发生的事实"，与 `session.save()` 区别：save 是内存镜像（历史可被压缩或丢弃），logger 是完整只写历史流。

```python
class SessionLogger(Protocol):
    async def log(self, session: Session) -> None: ...
```

规则：

1. `Agent.loggers: list[SessionLogger]`，由启动脚本按配置构造；可同时注入多个。
2. 调用时机：每轮 `_run_turn()` 结束后（含成功、取消、异常），在 compress 判据评估之前（§2.5 步骤 7.1）。
3. `SummaryNode` 不参与记录——它是对事实的摘要，不是事实本身。Logger 只记 `UserPromptNode`、`ToolCallNode`、`ToolResultNode`、`AssistantResponseNode`。
4. 内部状态 `last_tail_ids: dict[str, str]`：session_id → 上次成功 log 时的 `session.tail.id`。
5. 遍历算法：从 `session.tail` 向前回溯；遇 `id == last_tail_ids[session_id]` 停止（首次调用无 stop point，遍历整条链）；跳过 `SummaryNode`；按正序持久化；完成后更新 `last_tail_ids`。
6. Stop point 可达性：logger 在 compress 前调用，compress 至少保留 `keep_turns ≥ 1` 轮，所以上次 tail 始终在 preserve zone 内。

#### FileLogger

```yaml
loggers:
  - type: file
    filename: "session_{session_id}.jsonl"   # 支持 {session_id}；固定字符串则共享文件
```

实现要点：

1. `filename.format(session_id=session.id)` 解析路径；`~` 自动展开。
2. 文件存在时启动重建：逐行解析 JSON，按 `session_id` 分组取最后一条记录的 `id` 写入 `last_tail_ids`。
3. 每节点一行 JSON 追加：`{"session_id": ..., **node.to_dict()}`，复用现有节点序列化。
4. 每个实际文件路径一把 `asyncio.Lock`，保证并发安全。

## 3. Tools

agent 不关心 tool 来源（内置 / 配置加载 / 未来 MCP provider），统一为列出 / 调用两种能力。

### 3.1 共享类型

```python
AsyncToolFn = Callable[[dict[str, JSONValue]], Awaitable[JSONValue]]


@dataclass
class ToolArgDef:
    name: str
    type: str            # JSON Schema 类型
    desc: str
    required: bool = False


@dataclass
class ToolDef:
    desc: str
    args: list[ToolArgDef] = field(default_factory=list)


ToolMap = dict[str, ToolDef]   # key 是 tool name
```

约束：

1. `ToolDef` 不含 name（在 ToolMap key），不含 callable。
2. `ToolArgDef` 自动转 MCP `inputSchema`：顶层 `type: "object"`，字段填 `properties`，`required` 由 `required=True` 推导。
3. 当前只支持顶层 object + 一层平铺标量字段；无嵌套、数组、枚举、默认值。
4. tool 输入输出必须 JSON 可序列化。
5. `session_id` / `cwd` / `call_id` 不进 tool 函数签名，由 agent 内部管理。

### 3.2 ToolProvider

```python
class ToolProvider(Protocol):
    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]: ...
```

规则：

1. `__iter__` 逐个 yield `(name, tooldef, fn)`。
2. `fn` 签名固定 `async (args: dict[str, JSONValue]) -> JSONValue`。
3. 同步 tool 由 provider 自己 `asyncio.to_thread` 包装。
4. provider 不路由；路由由 `ToolManager`。

### 3.3 ToolRegistry

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

1. `register` name 冲突 raise `ValueError`。
2. `desc_tool(None)` 返回全集；`desc_tool(set())` 返回空（语义分离）；`desc_tool({...})` 返回指定子集，未注册名忽略。
3. `exclude` 从结果删除对应名：`result = (全集 if names is None else names) − (exclude or ∅)`。
4. `__getitem__(name)`：`name` 不存在 raise `KeyError`；调用方 `await registry[name](args)` 执行。
5. 执行失败通过异常表示，由 agent 编排层捕获处理（§2.3）。
6. 不对并发 tool 调用设上限。

### 3.4 内置 Tools

#### bash

- desc: `Execute a shell command and return stdout/stderr`
- 参数：`command`(string, req)、`cwd`(string)、`env`(object)、`stdin`(string)
- 返回：`{"stdout": str, "stderr": str, "returncode": int}`；超时返回 `returncode: -1`、stderr 含超时信息
- 实现：`asyncio.create_subprocess_shell` + `start_new_session=True` + `os.killpg`；默认 30s 超时；`env` 合并 `os.environ` 但拒绝 `LD_*`/`PATH`/`PYTHON*` 等危险变量。

#### create_task

- desc: `Create a sub-task with its own session and execute it`
- 参数：`prompt`(string, req)、`id`(int)、`depends`(array of int)、`tools`(array of string)、`inheritance`(bool, default false)
- 实现：子任务独立 `Session` 与主隔离；结果含 `output_text` / `stop_reason`；异常被捕获作 failed 返回；`inheritance=true` 时倒推到第一个非 frozen 节点 fork；每个 task 300s 超时；子任务 tool 集合排除 `create_task`。

#### http

- desc: `Send an HTTP request and return status, headers and body`
- 参数：`url`(string, req)、`method`(string, default GET)、`headers`(object)、`body`(string)、`timeout`(number, default 30)
- 返回：`{"status": int, "headers": {str: str}, "body": str}`；网络错误返回 `status: -1`
- 实现：`aiohttp.ClientSession`；body UTF-8 解码 errors=replace。

#### write_file

- desc: `Write content to a file, creating parent directories as needed`
- 参数：`path`(string, req)、`content`(string, req)、`encoding`(string, default utf-8)
- 自动创建父目录，覆盖写入；失败返回错误字符串。

#### edit_file

- desc: `Replace an exact string in a file`
- 参数：`path`(string, req)、`old_str`(string, req)、`new_str`(string, req)、`encoding`(string, default utf-8)
- 只替换首次出现；`old_str` 不存在时返回错误，不修改文件。

## 4. ACP 协议与 Frontend

frontend 实现 `Client`；`Agent` 持有 `Client` / `Backend` / `ToolRegistry` 及可选注入；`Session.prompt()` 推进对话；`Session` 通过 `Agent` 反向回调 `Client.update()`。`initialize` 由 `Agent.__init__` 隐式完成。

### 4.1 共享类型

```python
JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
ContentBlock = dict[str, JSONValue]

StopReason = Literal["end_turn", "cancelled"]
PromptReturn = tuple[StopReason, str]


@dataclass(slots=True)
class SessionUpdate:
    type: Literal["agent_message_chunk", "thinking_chunk", "tool_call", "tool_call_update"]
    data: dict[str, JSONValue]
```

约束：

1. `agent_message_chunk` 是模型最终输出；`thinking_chunk` 是模型思考。CLI 中两者分离输出，输出前 `strip()`。
2. `prompt()` 失败时直接抛异常，不返回 `failed`。

### 4.2 Client

```python
class Client(Protocol):
    async def update(self, session: "Session", update: SessionUpdate) -> None: ...
    async def request_permission(
        self, session: "Session", kind: str, payload: dict[str, JSONValue]
    ) -> bool: ...
```

ACP 映射：`update` ↔ `session/update`；`request_permission` ↔ `session/request_permission`。

约束：

1. 白名单、访问者鉴权属于 frontend / 启动脚本，不属于 agent 核心。
2. terminal、filesystem 等能力建模为 tools，不作为 client 方法。
3. `request_permission` 在 DEBUG 级别记录 `kind` 与 `payload`。

### 4.3 Agent

```python
class Agent(Protocol):
    def __init__(
        self,
        client: Client,
        backend: Backend,
        tools: ToolRegistry,
        compressor: "Compressor | None" = None,
        permissions: "PermissionChecker | None" = None,
        memory: "Memory | None" = None,
        loggers: list[SessionLogger] | None = None,
        compress_ratio: float = 0.75,
        context_window: int = 128000,
    ) -> None: ...

    async def new(self, cwd: str | None = None) -> "Session": ...
    async def load(self, data: JSONValue) -> "Session": ...
```

ACP 映射：`new` ↔ `session/new`；`load` ↔ `session/load`。

约束：

1. 不同 client 创建不同 agent 实例。
2. `permissions` 为 None 时内部默认为 `client`；其他可选注入未传时为 None。
3. backends 支持多个；agent 只持有名为 `primary` 的那个；compressor 是否独立 backend 由配置中是否存在 `backends.compressor` 决定。

### 4.4 Session

```python
class Session(Protocol):
    id: str
    cwd: str | None
    tail: Node | None

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

ACP 映射：`prompt` ↔ `session/prompt`；`cancel` ↔ `session/cancel`。`fork` / `compress` / `save` 是项目扩展。

约束：

1. `allowed_tools=None` 表示使用全部已注册 tool；传入列表时本轮 backend 仅可见该子集。
2. backend 返回 `tool_calls` 中不在允许列表的，按 §2.3 规则 4 写入 failed 不实际执行。
3. `fork()` 不接收 `from_node_id`，浅拷贝式分叉（§2.4）。
4. `Session` 内部维护 pending prompt 队列，容量 3；活跃 turn 存在时新 `prompt()` 入队，满抛 `SessionBusyError`。
5. 活跃 turn 存在时调用 `fork()` / `compress()` 抛异常。

### 4.5 CliClient

职责：实现 `Client` + `run(agent)`，处理取消、退出、`/` 命令；readline 集成（方向键、`~/.little_agent_history`、Tab 补全）。

stdin 架构：`_stdin_reader` 后台 task 通过 `asyncio.to_thread(input)` 阻塞读，结果送入 `_stdin_queue`（maxsize=32 兜底防 OOM）。`run()` 主循环在 agent 空闲时消费；prompt turn 期间并发的 `_watch_cancel_loop` 监听 `/cancel`，其他输入 put back。`_permission_done`（`asyncio.Event`）协调 `request_permission` 与 `_watch_cancel_loop` 防争抢。

显示规则：

1. `agent_message_chunk` 前缀 `[Agent]`；`thinking_chunk` 前缀 `[Thinking]`。
2. 输出前 `strip()`。
3. `tool_call` 显示 tool 名 + 多行 `k: v` 参数（非字符串值用 `json.dumps`）；超 5 行截断尾部并显示 `...{n} lines...`。

命令：`/quit` `/exit` `/cancel` `/fork` `/new` `/save <path>` `/load <path>` `/list-tools`。

### 4.6 WebClient

职责：

1. 持有 server-wide session 注册表 `_sessions: dict[str, Session]`。
2. 订阅模型路由：`_active: dict[ws, session_id | None]`，`update()` 只发给 `_active[ws] == session.id` 的连接。
3. 每轮 prompt 后 `session.save()` 落盘到 `{sessions_dir}/{session_id}.json`。
4. 启动时自动向 `agent.loggers` append 一个 FileLogger（路径 `{sessions_dir}/session_{session_id}.jsonl`）；用户配置的 logger 不被覆盖。
5. session_id 必须为 UUID v4 格式；非法即拒绝（防路径遍历）。
6. WebSocket Origin 校验：仅允许 null 或同源。

客户端消息：`session/list`、`session/new`、`session/resume`、`session/fork`、`session/delete`、`session/prompt`、`session/cancel`。`session/resume` 服务端先回 resume 确认，再发一条 `session/history`，节点数据来自 FileLogger 写入的 JSONL 文件。

持久化目录默认 `~/.local/state/little_agent/sessions/`，可通过 `frontend.sessions_dir` 覆盖。

## 5. Backend

backend 把 session 节点链转换为各 API 所需消息，把 API 响应映射回 `BackendTurnResult`。所有 backend 都是远程调用，不要求支持底层请求级 cancel。

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
    finish_reason: Literal["completed", "tool_call"]
    usage: dict[str, int] | None = None
    thinking_text: str | None = None
```

### 5.2 Backend 接口

```python
class Backend(Protocol):
    context_window: int

    def generate(
        self, session: "Session"
    ) -> AsyncIterator[SessionUpdate | BackendTurnResult]: ...
```

约束：

1. `generate()` 先 yield 零到多个 `SessionUpdate`，最后 yield 一个 `BackendTurnResult`。
2. backend 接收 `session`，自行读取链式历史并转换为后端输入；同时把 `session.get_turn_tool_map()` 转换为后端工具定义。
3. 流式 backend 用 streaming API，逐 chunk yield；流结束后 yield 最终 result。
4. 性能计数：`BackendTurnResult` yield 前 INFO 日志含 input/output token、cached_tokens、耗时。
5. DEBUG 日志：请求开始前记录完整 payload。
6. 超时：streaming 模式对整个流设超时，超时 raise `BackendTimeoutError`。
7. context-overflow：识别后 raise `ContextOverflowError`（`backends/exceptions.py`）；其他 `BadRequestError` 原样上抛。
8. `<think>` 标签处理（`OpenAIBackend` 专属）：标签外内容作 `agent_message_chunk`，标签内作 `thinking_chunk`；流结束时未闭合 `<think>` 按 thinking 处理。`reasoning_content` 路径不受影响。

### 5.3 并发控制

每个 backend 实例构造时按配置 `max_concurrency`（默认 1）初始化一把 `asyncio.Semaphore`。`generate()` 内部 acquire/release。调用方可并发 `generate()`，实际并发由 semaphore gate。

### 5.4 AnthropicBackend 专项

#### 节点链 → Anthropic messages

| 节点 | 转换 |
|------|------|
| `UserPromptNode` | `{role: user, content: prompt}` |
| `AssistantResponseNode`（无后续 tool call）| `{role: assistant, content: [{type: text, text}]}` |
| `AssistantResponseNode` + `ToolCallNode`（相邻）| 合并为一条 assistant，content = text(可选) + tool_use 块 |
| `ToolCallNode`（无前置 text）| `{role: assistant, content: [{type: tool_use, id, name, input}, ...]}` |
| `ToolResultNode` | `{role: user, content: [{type: tool_result, tool_use_id, content}, ...]}` |
| `SummaryNode`（链首）| 提升为 `system` 参数，不进 messages |
| `SummaryNode`（链中）| `{role: user, content: summary_text}` |

约束：assistant 与 user message 严格交替；`ToolResultNode` 紧接 `ToolCallNode` 所在 assistant message 后。

#### 工具定义

使用 `input_schema`（JSON Schema），由 `ToolMap` 转换。

#### 流式事件

`client.messages.stream()`：

| 事件 | emit |
|------|------|
| `text_delta` | `agent_message_chunk` |
| `thinking_delta` | `thinking_chunk` |
| `input_json_delta` | 累积到 tool_use，不 emit |
| `message_stop` | yield `BackendTurnResult` |

不解析 `<think>` 标签。

#### finish_reason

`end_turn` → `completed`；`tool_use` → `tool_call`。

#### Context overflow

捕获 `anthropic.BadRequestError`，message 大小写不敏感匹配 `"prompt is too long"` / `"too many tokens"` / `"maximum context length"` 时 raise `ContextOverflowError`。

#### 配置

| 字段 | 默认 | 说明 |
|------|------|------|
| `type` | — | 固定 `anthropic` |
| `model` | — | 必填 |
| `api_key` / `api_key_env` | — | 二选一；env 默认 `ANTHROPIC_API_KEY` |
| `system` | null | 不属于历史 |
| `context_window` | 128000 | 请求总长度上限，用于压缩触发判据 |
| `max_tokens` | 8192 | 单次响应输出 token 上限（独立维度，不等于 context_window）|
| `max_concurrency` | 1 | §5.3 |
| `base_url` | null | 可选 |

## 6. 其他

### 6.1 启动脚本

`pyproject.toml`：

```toml
[project.scripts]
little-agent = "little_agent.main:main"
```

`main()` 加载 YAML、初始化 logging（`logging.config.dictConfig`，`--loglevel` 覆盖根 logger）、构造 `ToolManager` / Backends / Compressor / Memory / SessionLogger 列表 / Client / Permission chain，注入 `AgentCore`，调 `client.run(agent)`。

### 6.2 配置 schema

```yaml
backends:
  primary:
    type: openai                         # 或 anthropic
    model: gpt-4
    api_key_env: OPENAI_API_KEY          # 或 api_key: <literal>
    base_url: https://api.openai.com/v1  # optional
    context_window: 128000               # optional, default 128000
    max_concurrency: 1                   # optional, default 1
    # anthropic 额外字段：
    # system: "You are a helpful assistant."   # optional
    # max_tokens: 8192                         # optional, 独立于 context_window
  compressor:                            # optional；缺省则与 primary 共用
    type: openai
    model: gpt-3.5-turbo
    api_key_env: OPENAI_API_KEY

agent:
  R: 0.75                                # 压缩触发阈值，(0,1]，默认 0.75

compressor:
  keep_turns: 3                          # 保留窗口，下限 1，默认 3
  compressed_window: 0.15                # W = compressed_window * primary.context_window，默认 0.15

tools:
  task_tool: true                        # default true；false 则不注册 create_task
  providers:
    - type: python
      module: my_tools.weather

# 列表为空或省略时，所有 tool 调用直接询问 client
permissions:
  - type: blackwhitelist
    blacklist: ["dangerous_*"]           # fnmatch；命中立即 deny
    whitelist: ["read_*"]                # fnmatch；命中立即 allow
  - type: yesman                         # 放行其余

frontend:
  type: cli                              # cli | web | acp
  # web 专有：
  # host: 127.0.0.1
  # port: 8080
  # sessions_dir: ~/.local/state/little_agent/sessions

loggers:                                 # optional；web 自动追加一个 FileLogger
  - type: file
    filename: "~/.local/state/little_agent/sessions/session_{session_id}.jsonl"

memory:                                  # optional
  type: file
  path: memory.jsonl
  backend: primary                       # 复用某个已配置 backend

logging:                                 # optional；缺省使用内置 dictConfig
  version: 1
  disable_existing_loggers: false
  formatters: {default: {format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"}}
  handlers: {console: {class: logging.StreamHandler, formatter: default, stream: "ext://sys.stdout"}}
  loggers: {"": {level: INFO, handlers: [console]}}
```

### 6.3 已知限制

1. `ToolArgDef` 只支持顶层 object + 一层平铺标量字段。
2. 不对并行 tool 调用设并发上限。
3. `save()` / `load()` 详细 schema 由实现确定，只确定需要序列化节点链表。
