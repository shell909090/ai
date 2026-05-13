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
3. `frontends ↔ agent` 稳定边界是 `Client`（§4）。`Client` Protocol 与 `Agent` / `Session` / `PermissionChecker` / `Hook` / `SessionUpdate` / `StopReason` / `PromptReturn` 等跨包契约一起住在 `little_agent/types.py`；frontends 实现 `Client`，agent 持有 `Client` 引用，无反向依赖。
4. `tools ↔ agent` 稳定边界是 `ToolProvider`（§3.2）：tools 模块（含外部插件）实现 `ToolProvider`，agent 通过它消费 tools。`ToolRegistry`（§3.3）也住在 `types.py`（其方法签名引用 `ToolProvider`），agent 提供默认实现 `ToolManager`；该 Protocol 是 agent 与外部 provider 之间的访问抽象。
5. `backends ↔ agent` 走项目内部接口（§5）。

## 2. Agent

### 2.1 消息节点

```python
@dataclass(slots=True)
class Node:
    id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    kind: ClassVar[str] = "node"


@dataclass(slots=True)
class UserPromptNode(Node):
    kind: ClassVar[str] = "user_prompt"
    prompt: str | list[ContentBlock] = ""


@dataclass(slots=True)
class AssistantNode(Node):
    kind: ClassVar[str] = "assistant"
    text: str = ""                      # 助手回复文本；tool call 时为调用前说明
    thinking: str = ""                  # 模型思考文本（reasoning/thinking），可为空
    tool_calls: dict[str, dict[str, Any]] = field(default_factory=dict)  # call_id -> {tool_name, arguments}；空表示无 tool call


@dataclass(slots=True)
class ToolResultNode(Node):
    kind: ClassVar[str] = "tool_result"
    results: dict[str, dict[str, Any]] = field(default_factory=dict)  # call_id -> {status, content}
```

规则：

1. `id` 用于 save/load、日志、调试、Hook 状态跟踪。节点无 `prev` 字段；顺序由 `SessionCore.messages` list 维护。
2. 节点整体逻辑 append-only；无显式冻结操作。`UserPromptNode` 和 `AssistantNode` 追加后内容不再变化。`ToolResultNode` 例外：追加时 `results` 为空，tools 并发执行期间原地回填，全部结果到位后才稳定。
3. `thinking` 字段持久化模型思考文本（来自 `BackendTurnResult.thinking_text`），用于 reload history 时还原 thinking bubble。仅作展示，不进 backend 历史回填。空字符串时序列化跳过该字段，节省体积。
4. 每个 Node 子类实现 `to_anthropic() -> list[dict[str, Any]]` 和 `to_openai() -> list[dict[str, Any]]`，把节点转换为对应 provider 的消息列表（空列表表示该节点不产生消息）。

### 2.2 Session 状态

`Session` 本身就是状态对象。最小状态：

1. `id`
2. `cwd`
3. `system_prompt: str | None`（会话级系统提示，初始化时从 `AgentCore.system_prompt` 复制）
4. `summaries: list[str]`（历史压缩摘要文本，按时间顺序）
5. `messages: list[Node]`（当前活跃消息列表，按时间顺序）
6. 是否存在活跃 turn
7. 当前 turn 是否已请求取消
8. pending prompt 队列（容量 3，满则抛 `SessionBusyError`）

并发规则：

1. 任何时刻，同一可变节点只能被一个 session 作为活跃尾节点持有。
2. fork 产生的新 session 浅拷贝 `messages` list 和 `summaries` list（节点本身已冻结不可变）。

### 2.3 Tool Call 与 Tool Result 节点约束

一组并行 tool calls 落为一个 `AssistantNode`（`tool_calls` 非空），紧接一个 `ToolResultNode` 承载结果。

`AssistantNode.tool_calls`：

```python
{"call_xxx": {"tool_name": str, "arguments": dict[str, Any]}}
```

`ToolResultNode.results`：

```python
{"call_xxx": {"status": "completed" | "failed" | "cancelled", "content": JSONValue}}
```

规则：

1. `AssistantNode`（tool call 时）由 backend 一次性写入后追加进 messages。
2. `ToolResultNode` 跟随其后创建，按 `call_id` 逐步回填。
3. 结果与状态依靠 `call_id` 对应，不依靠顺序。
4. tool 执行抛出的异常由编排层 `except Exception` 捕获，写入 `status="failed"`，`content` 为异常信息。**异常不冒出 prompt turn**。
5. 取消时未完成的 call 标记 `cancelled`，迟到结果丢弃。

### 2.4 fork 规则

1. `session.fork()` 基于当前 session 状态创建新 session。
2. 存在活跃 turn 时调用 fork 直接抛异常。
3. fork 实现：浅拷贝 `messages` list（`list(self.messages)`）、浅拷贝 `summaries` list、复制 `system_prompt`。节点不可变，浅拷贝安全。

### 2.5 编排流程

`Session.prompt()` 流程：

1. 已有活跃 turn：进入 pending 队列，满则抛 `SessionBusyError`；否则占据。
2. 追加 `UserPromptNode`。
3. 主循环（上限 `MAX_TURN_ITERATIONS=20`）：
   1. 调用 `Backend.generate(session)` 得到 async iterator。遍历产出：`SessionUpdate` 通过 `client.update()` 转发；`BackendTurnResult` 保存为 `result` 退出遍历；context-overflow 错误进入 §2.6.4 in-turn retry。遍历过程中记录 `did_stream`：若至少 yield 过一次 `agent_message_chunk`，则 frontend 已收到流式可见文本。
   2. `finish_reason == "completed"`：追加 `AssistantNode`（含 `text=output_text`、`thinking=thinking_text`、`tool_calls={}`）。仅在 `did_stream=False` 时补发一条全量 `agent_message_chunk`，避免与流式重复。返回 `("end_turn", output_text)`。
   3. `finish_reason == "tool_call"`：
      - `result.output_text` 非空时存入 `AssistantNode.text`；`result.thinking_text` 非空时存入 `AssistantNode.thinking`；`result.tool_calls` 存入 `AssistantNode.tool_calls`。
      - 追加 `AssistantNode`，通过 `Client.update` 通知 frontend。仅在 `did_stream=False` 且 `output_text` 非空时补发一条全量 `agent_message_chunk`，避免与流式重复。
      - 触发 `Hook.on_tool_call(session)`（此时 `session.messages[-1]` 为刚追加的 `AssistantNode`）。
      - 追加 `ToolResultNode`（results 初始为空，逐步回填）。
      - 检查每个 tool name 是否在 `allowed_tools` 内；不在则记 `failed`，不调用。
      - 通过 permission chain 检查；deny 则记 `failed`，不调用。
      - 并发执行允许的 tools（`asyncio.gather`），按 §2.3 写入。
      - 每个结果就位通过 `Client.update(tool_call_update)` 通知。
      - 触发 `Hook.on_tool_result(session)`（此时 `session.messages[-1]` 为已回填完成的 `ToolResultNode`）。
4. 超过 `MAX_TURN_ITERATIONS` 抛异常。
5. 收到 cancel：等当前 backend 调用结束，未完成 tool call 标 `cancelled`，返回 `("cancelled", partial_output)`。
6. 真正失败（backend 异常等）直接抛异常，不返回 `failed`。
7. finally 阶段：
   1. 若已注入 `hooks`，依次调用 `hook.on_turn_end(session)`（含成功、取消、异常路径；详见 §2.8）。
   2. 按 §2.6.2 评估是否触发 post-turn 自动压缩：
      - 触发：保留活跃 turn 标记，异步调度 compress 任务（`asyncio.create_task`），由该任务在结束时释放标记并唤醒 pending 队列。
      - 未触发：清理活跃 turn 标记；pending 队列非空则唤醒下一个。

`Session.cancel()`：无活跃 turn 直接返回；否则只设"已请求取消"标记，停止/冻结/收尾由 `prompt()` 协程完成；cancel 也作用于 post-turn compress 任务。

### 2.6 压缩

#### 2.6.1 Compressor 协议

```python
class Compressor(Protocol):
    async def compress(self, messages: list[Node]) -> tuple[list[str], list[Node]]: ...
```

规则：

1. 输入：当前 session 的完整 `messages` 列表（正序）。
2. 输出：`(summary_strs, remaining_messages)`。`summary_strs` 为本次压缩产生的摘要文本列表（空列表表示无操作，最多 3 条）；`remaining_messages` 为保留区节点列表。
3. 由启动脚本按配置构造，在 `Agent.__init__` 注入。
4. 配置中存在名为 `compressor` 的 backend 时使用它，否则与 agent 共用 backend。
5. `Session.compress()`：未注入 compressor 或存在活跃 turn 抛异常；否则调用 `compressor.compress(messages)` 后通过 `_apply_compress_result()` 更新 session 状态。
6. `Session._apply_compress_result(summaries, remaining)` 执行：① 将 summaries（列表）extend 到 `session.summaries`；② messages = remaining；③ 按 W-limit 裁剪旧 summaries（W-limit = `agent.compressed_window_tokens`，0 表示无限制）。
7. agent 编排在每次 turn 结束后自动评估并按需调度，详见 §2.6.2。

#### 2.6.2 自动触发策略

每次 `Session.prompt()` 即将返回前评估判据。命中则异步调度 compress 任务。

判据（任一即触发）：

1. **token 阈值（首选）**：本 turn 最后一次 backend 调用的 `usage.input_tokens + usage.output_tokens` 与该 backend 的 `context_window` 之比超过 `R`。`R` 由 agent 配置项 `R` 调整，默认 `0.75`，取值 (0, 1]。
2. **字符兜底**：本 turn 无有效 usage，累加 `session.messages` 各节点序列化字节数（UTF-8）除以 3 估算 token，比较 `R`。
3. **context-overflow 兜底**：见 §2.6.4。

#### 2.6.3 算法

参数：`keep_turns`（保留窗口，默认 3，下限 1）。W-limit 由 session 侧应用（见 §2.6.1 规则 6）。

turn 边界：从一条 `UserPromptNode` 起，到下一条 `UserPromptNode` 之前的所有节点。

`LLMCompressor.compress(messages)` 算法：

1. 找保留区起始：从 `messages` 头开始统计 `UserPromptNode` 数；若总 turn 数 ≤ `keep_turns` 则返回 `([], messages)`（no-op）。
2. **被压区**：`messages[:preserve_start]`（最近 `keep_turns` 个 turn 之前的所有节点）。
3. **保留区**：`messages[preserve_start:]`（最近 `keep_turns` 个 turn）。
4. **分批**：将被压区按 turn 切分后，分成至多 3 组（`_batch_turns`）；N ≤ 3 时每组一个 turn，N > 3 时均匀分配。
5. **压缩**：每组一次 LLM 调用，并发 `asyncio.gather`；每次调用前后各输出 INFO 日志（进入节点数/输出摘要字符数）。
6. 返回 `(summary_strs, preserve_zone)`，`summary_strs` 每组一条（最多 3 条）。

W-limit（在 `Session._apply_compress_result` 中执行）：`summaries` 超过 W-limit 时从头部丢弃旧摘要，至少保留 1 条。

#### 2.6.4 失败处理

- **post-turn 路径**：异常向 frontend 抛，session 状态不破坏（messages 不改变）。
- **in-turn overflow retry**：主循环中 backend 抛 `ContextOverflowError` 时，session 调用 `_apply_compress_result()` 更新自身，retry 当前 backend 调用一次；retry 仍 overflow 按普通异常上抛。

#### 2.6.5 日志

每次自动压缩输出 INFO：触发判据、估算 token、被压 turn 数、耗时。

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

### 2.8 Hooks

会话生命周期 hook 系统，挂载到 session 的多个时点。Hook 与 `session.save()` 的区别：save 是内存镜像（历史可被压缩或丢弃），hook 是事件级旁路通道，订阅者各自决定如何持久化或反应。原 SessionLogger 是 hook 系统的特例（只关心 turn 结束），现统一为基类 + 默认空实现的形式，便于未来扩展更多挂载点（如 search、metrics、external observability）。

接口（基类 + 默认空实现，订阅者继承后只 override 关心的方法）。`Hook` 类位于 `little_agent/types.py`，所有方法只接收 `session`——不向 hook 注入额外 `Node` 参数；需要节点数据的 hook 通过 `session.messages[-1]` 读取当前尾节点。Hook 基类不引用任何 `Node` 子类，保持在 types.py 中无 agent 反向耦合。

```python
class Hook:
    """Lifecycle hook. Override only the events you care about."""

    async def on_session_new(self, session: Session) -> None: pass
    async def on_turn_start(self, session: Session) -> None: pass
    async def on_turn_end(self, session: Session) -> None: pass
    async def on_tool_call(self, session: Session) -> None: pass
    async def on_tool_result(self, session: Session) -> None: pass
    async def on_compress(self, session: Session) -> None: pass
    async def on_fork(self, source: Session, forked: Session) -> None: pass
    async def on_cancel(self, session: Session) -> None: pass
```

规则：

1. `Agent.hooks: list[Hook]`，由启动脚本按配置构造；可同时注入多个；遍历顺序即配置顺序。
2. 调用时机：

   | Hook 方法 | 触发时机 | 此时 `session.messages[-1]` |
   |---|---|---|
   | `on_session_new(session)` | `Agent.new()` 创建 session 后（AGENTS.md 已写入 system_prompt） | messages 为空 |
   | `on_turn_start(session)` | §2.5 步骤 2 之前（追加 `UserPromptNode` 之前） | 上一轮最后一个节点（或 messages 为空） |
   | `on_turn_end(session)` | §2.5 步骤 7.1（compress 判据评估之前），含成功 / 取消 / 异常路径 | 本轮最后一个节点 |
   | `on_tool_call(session)` | §2.5 步骤 3.3 中 `AssistantNode` 追加后，且在创建 `ToolResultNode` 之前 | 刚追加的 `AssistantNode` |
   | `on_tool_result(session)` | §2.5 步骤 3.3 中 `ToolResultNode` 全部结果回填后 | 已回填完成的 `ToolResultNode` |
   | `on_compress(session)` | compress 任务（post-turn 异步或 in-turn retry）完成后 | 保留区首个节点（`UserPromptNode`） |
   | `on_fork(source, forked)` | `Session.fork()` 成功创建新 session 后 | 不变 |
   | `on_cancel(session)` | turn 被取消后；随后 `on_turn_end` 仍会在 finally 中触发 | 最后一个节点 |

3. 异常隔离：单个 hook 抛异常不阻断主流程；编排层对每次 hook 调用 `try/except`，异常以 ERROR 级别记入日志（含 hook 类名、`session_id`、`turn_id`），继续下一个 hook。
4. 多 hook 顺序：按配置顺序串行调用；不并发，避免共享状态竞争。
5. 压缩结果以字符串形式存入 `session.summaries`，不作为节点追加进 `messages`；关心压缩事件的 hook 使用 `on_compress`，不需要从节点链识别压缩行为。

#### SessionJSONLStore（plugin：同时实现 Hook + ToolProvider）

将节点链以 JSONL 形式持久化到文件，并在同一类上暴露 `search_session` 工具供 agent 主动回查。它是当前唯一一个跨「Hook 注册点」与「Tool 注册点」的组件——一个实例同时挂到 `agent.hooks` 与 `ToolRegistry`。

**这是一个新的注册范式（暂称 plugin）**：单一组件同时占用多个注册点。当前仅 `SessionJSONLStore` 一例，不抽象通用 plugin 机制；未来若同类组件增多再考虑抽象。

接口：

```python
class SessionJSONLStore(Hook, ToolProvider):
    def __init__(self, sessions_dir: str, filename_template: str = "{session_id}_session.jsonl"):
        ...

    # Hook 接口：唯一 override on_turn_end
    async def on_turn_end(self, session: Session) -> None:
        # 增量遍历自上次 tail 起的新节点，append 到 JSONL
        ...

    # ToolProvider 接口：yield search_session 工具
    def __iter__(self) -> Iterator[tuple[str, ToolDef, AsyncToolFn]]:
        async def search_session_fn(args: dict[str, JSONValue]) -> JSONValue:
            session_id = current_session_id.get()
            return await self._search(session_id, **args)
        yield ("search_session", _SEARCH_TOOLDEF, search_session_fn)

    # 共享内部
    async def _append_node(self, session_id: str, node_dict: dict) -> None: ...
    async def _search(self, session_id: str, query: str, kind: str = "turn", limit: int = 5) -> list[Hit]: ...
    async def load_history(self, session_id: str) -> list[NodeRecord]: ...   # 供 §4.6 web `session/resume` 调用
```

**注册规则**：启动脚本检测顶层 `session_store:` 配置段：

- **存在**：实例化 `SessionJSONLStore(**session_store)`，同时 `agent.hooks.append(store)` 和 `tool_registry.register(store)`。
- **缺省**：不实例化；hook 与 tool 双方都不出现 `SessionJSONLStore`。
- **Web frontend 特例**：用户未配置 `session_store:` 但启用了 web frontend 时，启动脚本以默认参数（`sessions_dir=~/.local/state/little_agent/sessions/`）自动实例化并注入，日志 INFO 提示「session_store auto-enabled for web frontend」。

**Hook 侧行为**（与原 FileLogger 一致）：

1. 仅 override `on_turn_end`；其他 hook 方法走 `Hook` 基类默认 no-op。
2. 内部状态 `last_tail_ids: dict[str, str]`：session_id → 上次成功记录时的尾节点 id。
3. 遍历算法：`on_turn_end` 触发时从 `session.messages[-1]` 向前遍历；遇 `id == last_tail_ids[session_id]` 停止（首次调用无 stop point，遍历整条链）；按正序持久化；完成后更新 `last_tail_ids`。
4. Stop point 可达性：`on_turn_end` 在 compress 之前触发（§2.5 步骤 7.1），compress 至少保留 `keep_turns ≥ 1` 轮，所以上次记录的尾节点 id 始终在 preserve zone 内。
5. `filename_template.format(session_id=session.id)` 解析路径，相对路径基于 `sessions_dir`；`~` 自动展开。
6. 文件存在时启动重建：逐行解析 JSON，按 `session_id` 分组取最后一条记录的 `id` 写入 `last_tail_ids`。
7. 每节点一行 JSON 追加：`{"session_id": ..., **node.to_dict()}`，复用现有节点序列化。
8. 写端：每个实际文件路径一把 `asyncio.Lock`，保证并发追加安全。

**Tool 侧行为**（`search_session` 工具实现请见 §3.4）：

- 读端不持锁；JSONL 是 append-only，open→readlines→close 即可；尾部半行解析失败时跳过（容忍 writer 写到一半的情况）。
- `current_session_id` 从 `little_agent/context.py` 的 ContextVar 读取，与编排层 turn-scoped context 一致。

## 3. Tools

agent 不关心 tool 来源（内置 / 配置加载 / 未来 MCP provider），统一为列出 / 调用两种能力。

**模块归属**：`ToolProvider`、共享类型（`ToolDef` / `ToolMap` / `AsyncToolFn` / `ToolArgDef`）与具体 tool 实现位于 `little_agent/tools/`。`ToolRegistry` 协议本身住在 `little_agent/types.py`（与其它跨包契约同处），其默认实现 `ToolManager` 与 per-turn 调用流水线函数 `invoke_turn_tools()`、装配工厂 `build_tools` / `parse_mcp_configs` / `start_mcp_providers` 位于 `little_agent/agent/tool_manager.py` 与 `little_agent/agent/tool_setup.py`。这些 agent 侧实现不对 tools 模块暴露。

### 3.1 共享类型

```python
AsyncToolFn = Callable[[dict[str, JSONValue], Session], Awaitable[JSONValue]]


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
5. `session` 通过参数传入；`call_id` / `cwd` 不进签名，由 agent 内部管理。

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
- 参数：`command`(string, req)、`cwd`(string)、`env`(object)、`stdin`(string)、`timeout`(integer, 覆盖默认超时秒数，受 `max_timeout` 上限保护)
- 返回：`{"stdout": str, "stderr": str, "returncode": int}`；超时返回 `returncode: -1`、stderr 含超时信息
- 实现：`asyncio.create_subprocess_shell` + `start_new_session=True` + `os.killpg`；`env` 合并 `os.environ` 但拒绝 `LD_*`/`PATH`/`PYTHON*` 等危险变量。
- 构造参数（通过 `tools.providers` dict 传入）：

| 字段 | 默认 | 说明 |
|------|------|------|
| `timeout` | 30 | 默认超时秒数 |
| `max_timeout` | 1800 | 单次调用允许的最大超时秒数；tool 参数超过此值时夹回并 WARNING |

- 启动配置示例：
  ```yaml
  tools:
    providers:
      little_agent.tools.bash.BashToolProvider:
        timeout: 600
        max_timeout: 3600
  ```

#### task

- desc: `Create a sub-task with its own session and execute it`
- 参数：`prompt`(string, req)、`id`(int)、`depends`(array of int)、`tools`(array of string)、`inheritance`(bool, default false)
- 实现：子任务独立 `Session` 与主隔离；结果含 `output_text` / `stop_reason`；异常被捕获作 failed 返回；`inheritance=true` 时去掉当前正在回填的 `ToolResultNode`（`messages[:-1]`）后 fork，再补一个占位 `ToolResultNode` 满足 API 对 tool_use/tool_result 配对的要求；每个 task 300s 超时；子任务 tool 集合排除 `task`。

#### http

- desc: `Send an HTTP request and return status, headers and body`
- 参数：`url`(string, req)、`method`(string, default GET)、`headers`(object)、`body`(string)、`timeout`(number, default 30)
- 返回：`{"status": int, "headers": {str: str}, "body": str}`；网络错误返回 `status: -1`
- 实现：`aiohttp.ClientSession`；body UTF-8 解码 errors=replace。

#### edit_file

`Create, overwrite, or partially edit a file`

参数：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `path` | string | — | 必填，文件路径 |
| `new_str` | string | — | 必填，写入/插入/替换的内容；空字符串 = 删除 |
| `old_str` | string | null | 字符串定位；与 `pos` 互斥 |
| `pos` | integer | null | 字符位置（0-indexed），`-1` = 文件尾；与 `old_str` 互斥 |
| `len` | integer | 0 | 与 `pos` 配合的替换字符数；`0` = 纯插入 |
| `create` | boolean | false | 文件不存在时是否自动创建（含父目录） |
| `encoding` | string | utf-8 | 文件编码 |

操作模式（三选一）：

- 均不提供 `old_str` / `pos`：全量覆写。
- `old_str`：替换首次出现；不存在则返回错误且不修改文件。
- `pos`：`(0, 0)` 头部插入；`(-1, 0)` 尾部追加；`(N, M)` 区间替换。

错误处理：

- `old_str` 与 `pos` 同时提供 → raise `ValueError`。
- 文件不存在且 `create=false` → 返回错误字符串。

#### search_session

由 §2.8 `SessionJSONLStore` plugin 的 `ToolProvider` 侧暴露，仅在顶层配置 `session_store:` 存在（或 web frontend 自动启用）时注册。配合「`session.summaries` 作历史摘要、`search_session` 作 JSONL 正文检索」分工：compressor 把旧 turn 压缩为摘要字符串存入 `session.summaries` 后，AI 通过本工具按需从 JSONL 文件检索原始内容。

- desc: `Search this session's history (including turns evicted from active context) by keyword`
- 参数：

  | 字段 | 类型 | 默认 | 说明 |
  |------|------|------|------|
  | `query` | string | — | 必填；子串关键字；空串视为无文本过滤（与 `kind` 配合返回最新 N） |
  | `limit` | integer | 5 | 返回结果数上限 |
  | `kind` | string | `turn` | 见下表 |

- `kind` 取值：

  | 值 | 匹配粒度 | 返回粒度 |
  |---|---|---|
  | `turn`（默认） | query 对 turn 内所有节点文本拼接做子串匹配 | 整个 turn（含全部节点） |
  | `any` | query 对单节点文本做子串匹配，不限节点类型 | 命中的单个节点 |
  | `user_prompt` / `assistant` / `tool_result` | query 对该类型节点文本做子串匹配 | 命中的单个节点 |

- 返回结构：

  ```python
  # kind == "turn"
  {"turn_id": str, "created_at": str, "nodes": [{"kind": str, "snippet": str}, ...]}

  # 其他 kind
  {"turn_id": str, "node_id": str, "kind": str, "created_at": str, "snippet": str}
  ```

- `turn_id` 统一为该 turn 的 `UserPromptNode.id`。
- Snippet 截断到合理上限（建议 500 字符），避免单次返回过大。
- 匹配实现：case-insensitive 子串；时间倒序（最新匹配排前）；超过 `limit` 后停止扫描。空 query 时 `kind=turn` 返回最近 `limit` 个 turn、`kind=any` 返回最近 `limit` 个节点。
- 数据源：`SessionJSONLStore` 写入的 per-session JSONL；通过 `current_session_id` ContextVar 定位当前文件。JSONL 不存在时返回空列表，不抛异常。

### 3.5 MCP Provider

**stdio 子进程模型**：`MCPStdioProvider` 实现 `ToolProvider` 协议，通过官方 `mcp` SDK（PyPI: `mcp`）以 stdio 传输连接 MCP 服务器子进程。调用 `start()` 握手并缓存 `tools/list`；调用 `stop()` 终止子进程。

**命名空间规则**：MCP 服务器 `weather` 暴露的 tool `get_temp` 在 `ToolRegistry` 中注册为 `weather__get_temp`（双下划线前缀），满足 `^[a-zA-Z0-9_-]{1,64}$` 正则要求。超长或字符非法时 WARNING 跳过该 tool。

**schema 转换**：`inputSchema` 必须为顶层 `type: object` + 一层平铺标量字段（string/integer/number/boolean）；遇到嵌套、数组等不支持字段时记 WARNING 并跳过整个 tool（其余 tool 不受影响）。

**生命周期**：`main.py` 在进入 async 主循环前 `await provider.start()`；退出时 `await provider.stop()`。子进程崩溃后调用返回 failed，不重启。任一 provider 启动失败只记 ERROR，不阻断其他 provider。

**配置（见 §6.2 `tools.mcp` 段）**：`env` 为 None 时子进程 env 为空（不继承 os.environ）；`cwd` 可选。

## 4. ACP 协议与 Frontend

frontend 实现 `Client`；`Agent` 持有 `Client` / `Backend` / `ToolRegistry` 及可选注入；`Session.prompt()` 推进对话；`Session` 通过 `Agent` 反向回调 `Client.update()`。`initialize` 由 `Agent.__init__` 隐式完成。

### 4.1 共享类型

`little_agent/types.py` 是项目的"契约层"——所有跨包契约都住在这里。运行时它是 leaf（不 import 任何项目内模块）；`ToolRegistry` 因为方法签名引用 `tools.protocol` 的类型，通过 TYPE_CHECKING 拿到这些符号，运行期无依赖。

types.py 提供：

- **JSON 原语**：`JSONScalar` / `JSONValue` / `ContentBlock`
- **运行时事件**：`SessionUpdate`
- **运行时约定**：`StopReason` / `PromptReturn`
- **跨包 Protocol**：`Agent` / `Session` / `Client` / `PermissionChecker` / `ToolRegistry`
- **lifecycle 基类**：`Hook`（基类 + 空实现，不是 Protocol）

唯一不在 types.py 的项目内 Protocol 是 `Compressor`——它的方法签名引用 `Node`（agent 内部数据结构），因此它和实现 `LLMCompressor` 同住 `little_agent/agent/compressor.py`。

```python
# little_agent/types.py
JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
ContentBlock = dict[str, JSONValue]

StopReason = Literal["end_turn", "cancelled"]
PromptReturn = tuple[StopReason, str]


@dataclass
class SessionUpdate:
    type: Literal["agent_message_chunk", "thinking_chunk", "tool_call", "tool_call_update"]
    data: dict[str, JSONValue]
```

约束：

1. `agent_message_chunk` 是模型最终输出；`thinking_chunk` 是模型思考。CLI 中两者分离输出，输出前 `strip()`。
2. `prompt()` 失败时直接抛异常，不返回 `failed`。
3. `SessionUpdate` 是 frontend ↔ agent 与 backend ↔ agent 共用的事件载体：backends 在 `generate()` 中 yield；agent 的 turn 编排（`turn_runner` 与 `tool_manager.invoke_turn_tools`）也直接构造并通过 `Client.update()` 转发给 frontend。由 types.py 定义、双侧消费。

### 4.2 Client

`Client` Protocol 定义在 `little_agent/types.py`（与 `Session` / `Agent` 等并列），由 agent 持有引用、由 frontend 实现。frontends 包不保留独立的 `protocol.py`。

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
        hooks: list[Hook] | None = None,
        compress_threshold: float = 0.75,
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
    system_prompt: str | None
    summaries: list[str]
    messages: list[Node]

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

职责：实现 `Client` + `run(agent)`，处理取消、退出、`/` 命令；使用 `prompt_toolkit` 提供 async input、历史（`~/.little_agent_history`）、Tab 补全。

stdin 架构：`CliClient` 持有一个 `prompt_toolkit.PromptSession`（注入以便测试 mock）。`run()` 主循环调用 `prompt_session.prompt_async("> ")`；agent 执行期间通过 `asyncio.create_task` + `try/except KeyboardInterrupt` 捕获 Ctrl-C 并调 `session.cancel()`；`request_permission` 直接调 `prompt_session.prompt_async("[Allow x? y/N] ")`，无需 stdin 队列或事件协调。`patch_stdout()` 保证 agent 流式输出不破坏 prompt 行。

显示规则：

1. `agent_message_chunk` 前缀 `[Agent]`；`thinking_chunk` 前缀 `[Thinking]`。
2. 输出前 `strip()`。
3. `tool_call` 显示 tool 名 + 多行 `k: v` 参数（非字符串值用 `json.dumps`）；超 5 行截断尾部并显示 `...{n} lines...`。

命令（idle 期间输入）：`/quit` `/exit` `/fork` `/new` `/save <path>` `/load <path>` `/list-tools` `/compact`。取消：Ctrl-C（agent 执行期）或 `KeyboardInterrupt`（idle 期退出）。`/cancel` 作为 `/cancel` 命令仍有效（等价于 Ctrl-C，在 idle 期间输入无实际 agent 可取消时静默忽略）。

`/compact`：调用 `session.compress()`；无 compressor 或存在活跃 turn 时捕获异常并打印错误，不退出。

### 4.6 WebClient

职责：

1. 持有 server-wide session 注册表 `_sessions: dict[str, Session]`。
2. 订阅模型路由：`_active: dict[ws, session_id | None]`，`update()` 只发给 `_active[ws] == session.id` 的连接。
3. 每轮 prompt 后 `session.save()` 落盘到 `{sessions_dir}/{session_id}.json`。
4. 启动时若用户未配置顶层 `session_store:`，启动脚本以默认参数（`sessions_dir = frontend.sessions_dir` 或 `~/.local/state/little_agent/sessions/`）自动实例化 `SessionJSONLStore` plugin 并同时注入 `agent.hooks` 与 `ToolRegistry`，日志 INFO 提示「session_store auto-enabled for web frontend」；用户已配置则不覆盖。`session/resume` 通过 store 的 `load_history()` 读取节点链。
5. session_id 必须为 UUID v4 格式；非法即拒绝（防路径遍历）。
6. WebSocket Origin 校验：仅允许 null 或同源。

客户端消息：`session/list`、`session/new`、`session/resume`、`session/fork`、`session/delete`、`session/prompt`、`session/cancel`、`session/compact`。`session/resume` 服务端先回 resume 确认，再发一条 `session/history`，节点数据来自 `SessionJSONLStore` plugin 写入的 JSONL 文件。

`session/compact`：服务端调用 `sess.compress()`，返回 `{"type": "session/compact_response", "ok": true}` 或 `{"type": "session/compact_response", "ok": false, "error": "..."}`。存在活跃 turn 或无 compressor 时返回 `ok: false`。前端收到 `ok: true` 后在聊天区插入系统提示消息（`--- Context compressed ---`）；收到 `ok: false` 时显示错误，不插入提示。Compact 按钮执行期间禁用，收到响应后恢复。

持久化目录默认 `~/.local/state/little_agent/sessions/`，可通过 `frontend.sessions_dir` 覆盖。

**静态资源**：前端 TypeScript 源码位于顶层 `frontend/`，构建产物输出到 `frontend/dist/`，通过 `make package-static` 拷贝到 `little_agent/_static/`（package data）。运行时 `server.py` 优先从 `little_agent/_static/` 提供静态文件；若未构建则回落到旧路径 `little_agent/frontends/static/`（兼容）。`frontend.static_dir` 配置项（待实现）可覆盖路径，便于开发时指向 `frontend/dist/`。

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
class BackendSession(Protocol):
    """Backend.generate() 所需的最小 session 契约。"""
    id: str
    system_prompt: str | None
    summaries: list[str]
    messages: list[Node]
    def get_turn_tool_map(self) -> ToolMap: ...


class Backend(Protocol):
    context_window: int

    def generate(
        self, session: BackendSession
    ) -> AsyncIterator[SessionUpdate | BackendTurnResult]: ...
```

约束：

1. `generate()` 先 yield 零到多个 `SessionUpdate`，最后 yield 一个 `BackendTurnResult`。
2. backend 接收 `BackendSession`，遍历 `session.messages`，对每个节点调用 `node.to_anthropic()` / `node.to_openai()` 取得 provider 特定消息列表，并按需做整合（summaries 注入 system 参数、assistant/user 序列拼装）；同时把 `session.get_turn_tool_map()` 转换为后端工具定义。
3. `Backend.generate()` 的形参类型是 `BackendSession`（最小化输入契约），不是完整的 `Session`。这样 compressor 等无需活跃 turn / pending queue / fork 状态 / agent 引用的调用方可以直接提供轻量 `BackendSession` 实现，不必伪造 agent 上下文。`SessionCore` 天然满足 `BackendSession`。
4. 流式 backend 用 streaming API，逐 chunk yield；流结束后 yield 最终 result。
5. 性能计数：`BackendTurnResult` yield 前 INFO 日志含 input/output token、cached_tokens、耗时。
6. DEBUG 日志：请求开始前记录完整 payload。
7. 超时：streaming 模式对整个流设超时，超时 raise `BackendTimeoutError`。
8. context-overflow：识别后 raise `ContextOverflowError`（`backends/exceptions.py`）；其他 `BadRequestError` 原样上抛。
9. `<think>` 标签处理（`OpenAIBackend` 专属）：标签外内容作 `agent_message_chunk`，标签内作 `thinking_chunk`；流结束时未闭合 `<think>` 按 thinking 处理。`reasoning_content` 路径不受影响。

### 5.3 并发控制

每个 backend 实例构造时按配置 `max_concurrency`（默认 1）初始化一把 `asyncio.Semaphore`。`generate()` 内部 acquire/release。调用方可并发 `generate()`，实际并发由 semaphore gate。

### 5.4 AnthropicBackend 专项

#### 节点链 → Anthropic messages

下表的逐节点转换在 `Node.to_anthropic()` 上实现（§2.1 规则 4）；本节定义 backend 层负责的整合规则：summaries 注入、消息序列拼装、assistant/user 交替约束。

压缩摘要（`session.summaries`）不作为节点存在于 `messages` 中；backend 在 `_chain_to_messages()` 里将 `session.system_prompt` 与 `session.summaries` 拼接为 `effective_system`，作为 API 的 `system` 参数传入。

| 节点 | 转换 |
|------|------|
| `UserPromptNode` | `{role: user, content: prompt}` |
| `AssistantNode`（`tool_calls` 为空）| `{role: assistant, content: [{type: text, text}]}` |
| `AssistantNode`（`tool_calls` 非空）| `{role: assistant, content: text(可选) + tool_use 块}` |
| `ToolResultNode` | `{role: user, content: [{type: tool_result, tool_use_id, content}, ...]}` |

约束：assistant 与 user message 严格交替；`ToolResultNode` 紧接前一个 `AssistantNode` 之后。`AssistantNode.thinking` 不参与 messages 回填，仅供前端 reload history 时还原 thinking bubble。

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

`main()` 加载 YAML、与内置 `_DEFAULT_CONFIG` 深度合并（用户配置优先，缺省字段由默认值补全）、初始化 logging（`logging.config.dictConfig`，`--loglevel` 覆盖根 logger）、构造 `ToolManager` / Backends / Compressor / Hook 列表 / Client / Permission chain，注入 `AgentCore`，调 `client.run(agent)`。

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
  compress_threshold: 0.75               # 压缩触发阈值，(0,1]，默认 0.75
  max_tool_result_chars: 50000           # tool result 截断上限（JSON 序列化字符数），默认 50000；超出时截断并附 [TRUNCATED] 标注
  ignore_agentsmd: false                 # 为 true 时跳过 AGENTS.md 查找（开发目录下自带 AGENTS.md 时使用）

compressor:
  keep_turns: 3                          # 保留窗口，下限 1，默认 3
  compressed_window: 0.15                # W = compressed_window * primary.context_window，默认 0.15

tools:
  providers:
    little_agent.tools.bash.BashToolProvider:        # 默认注入；设为 null 可禁用
      timeout: 30
      max_timeout: 1800
    little_agent.tools.task.TaskToolProvider: {}     # 默认注入（特例：需 agent 引用，main.py 专用注册路径）；设为 null 可禁用
    little_agent.tools.http.HttpToolProvider: {}
    little_agent.tools.file.EditFileToolProvider: {}
    my_tools.weather.WeatherProvider:
      api_key_env: WEATHER_KEY
  mcp:                                     # optional；每个条目自动实例化 MCPStdioProvider（§3.5）
    weather:                               # server name；用作工具名前缀 weather__get_temp
      command: ["npx", "-y", "@modelcontextprotocol/server-weather"]
      env:                                 # optional；子进程 env；None 时 env 为空
        WEATHER_API_KEY: "${WEATHER_API_KEY}"
      cwd: "/optional/working/dir"         # optional
    filesystem:
      command: ["python", "-m", "mcp_filesystem", "--root", "/data"]

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

session_store:                           # optional plugin（同时挂 hooks + tools）；存在即启用
  sessions_dir: ~/.local/state/little_agent/sessions/
  filename_template: "{session_id}_session.jsonl"
  # web frontend 启用且未配置 session_store 时，启动脚本自动以默认参数实例化（§4.6）。

hooks:                                   # optional；保留作未来自定义 Hook 注册扩展点
                                         # 当前无内置 Hook 子类通过此段注册（SessionJSONLStore 走 session_store: 段）

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
