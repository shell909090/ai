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
    thinking: str = ""                  # 模型思考文本（reasoning/thinking），可为空
    frozen: bool = False


@dataclass(slots=True)
class ToolCallNode(Node):
    kind: ClassVar[str] = "tool_call"
    output_text: str                    # tool call 前的 reasoning/说明，可为空
    thinking: str = ""                  # 模型思考文本（reasoning/thinking），可为空
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

1. 运行时通过 `prev` 对象引用回溯。`id` 用于 save/load、日志、调试、fork 入口、Hook 状态跟踪。
2. 节点整体逻辑 append-only。
3. `frozen` 字段只出现在写入过程中可变的节点：`AssistantResponseNode`、`ToolResultNode`。其他节点创建即不可变。
4. 可变节点在任意时刻只能被一个 session 作为活跃尾节点持有。
5. 触发冻结的时机（由 session 管理）：
   - 追加新节点时旧尾若可变，立刻冻结。
   - session 被 fork 时当前尾若可变，立刻冻结。
   - 当前 turn 结束或被取消时，尾节点立刻冻结。
6. `thinking` 字段持久化模型思考文本（来自 `BackendTurnResult.thinking_text`），用于 reload history 时还原 thinking bubble。仅作展示，不进 backend 历史回填（`Node.to_anthropic()` / `Node.to_openai()` 只读 `text` / `output_text`）。空字符串时序列化跳过该字段，节省体积。
7. 每个 Node 子类实现 `to_anthropic() -> list[dict[str, Any]]` 和 `to_openai() -> list[dict[str, Any]]`，把节点转换为对应 provider 的消息列表（空列表表示该节点不产生消息）。把"chain → provider messages"的逐节点知识固化在节点自身，避免分散到各 backend 实现。Provider 特定的整合逻辑（如 Anthropic 把链首 `SummaryNode` 提升为 `system` 参数、assistant/user 序列拼装）由 backend 层完成（§5）。

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
   1. 调用 `Backend.generate(session)` 得到 async iterator。遍历产出：`SessionUpdate` 通过 `client.update()` 转发；`BackendTurnResult` 保存为 `result` 退出遍历；context-overflow 错误进入 §2.6.4 in-turn retry。遍历过程中记录 `did_stream`：若至少 yield 过一次 `agent_message_chunk`，则 frontend 已收到流式可见文本。
   2. `finish_reason == "completed"`：追加 `AssistantResponseNode`（含 `text=output_text`、`thinking=thinking_text`，冻结）。仅在 `did_stream=False` 时补发一条全量 `agent_message_chunk`，避免与流式重复。返回 `("end_turn", output_text)`。
   3. `finish_reason == "tool_call"`：
      - `result.output_text` 非空时存入 `ToolCallNode.output_text`；`result.thinking_text` 非空时存入 `ToolCallNode.thinking`。
      - 追加 `ToolCallNode`（冻结），通过 `Client.update` 通知 frontend。仅在 `did_stream=False` 且 `output_text` 非空时补发一条全量 `agent_message_chunk`，避免与流式重复。
      - 触发 `Hook.on_tool_call(session)`（此时 `session.tail` 指向刚冻结的 `ToolCallNode`）。
      - 追加 `ToolResultNode`（可变）。
      - 检查每个 tool name 是否在 `allowed_tools` 内；不在则记 `failed`，不调用。
      - 通过 permission chain 检查；deny 则记 `failed`，不调用。
      - 并发执行允许的 tools（`asyncio.gather`），按 §2.3 写入。
      - 每个结果就位通过 `Client.update(tool_call_update)` 通知。
      - 全部结果到位或 turn 取消后，`ToolResultNode` 冻结。
      - 触发 `Hook.on_tool_result(session)`（此时 `session.tail` 指向刚冻结的 `ToolResultNode`）。
4. 超过 `MAX_TURN_ITERATIONS` 抛异常。
5. 收到 cancel：等当前 backend 调用结束，未完成 tool call 标 `cancelled`，节点冻结，返回 `("cancelled", partial_output)`。
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

**关键不变式**：`SummaryNode` 只出现在已压缩区（鏈头一侧的连续段），不混入活跃对话节点之间。步骤 1 的「从 tail 往前回溯找到第一条 SummaryNode 即作為壓縮區上界」依赖此不变式——一旦 SummaryNode 出现在活跃区中间，上界判定就会错误。任何其他机制（如 memory 注入）都不得在活跃区插入 SummaryNode；session 内确需在 context 之外保留信息的，应通过工具层（如后续的 session 搜索工具）按需检索，而非注入节点。

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

### 2.8 Hooks

会话生命周期 hook 系统，挂载到 session 的多个时点。Hook 与 `session.save()` 的区别：save 是内存镜像（历史可被压缩或丢弃），hook 是事件级旁路通道，订阅者各自决定如何持久化或反应。原 SessionLogger 是 hook 系统的特例（只关心 turn 结束），现统一为基类 + 默认空实现的形式，便于未来扩展更多挂载点（如 search、metrics、external observability）。

接口（基类 + 默认空实现，订阅者继承后只 override 关心的方法）。`Hook` 类位于 `little_agent/types.py`，所有方法只接收 `session`——不向 hook 注入额外 `Node` 参数，因为每个 callback 触发时 `session.tail` 已经指向当下相关的那个 node；需要原 node 数据的 hook 直接读 `session.tail`（必要时回溯 `tail.prev`）。这样 Hook 基类不引用任何 `Node` 子类，保持在 types.py 中无 agent 反向耦合。

```python
class Hook:
    """Lifecycle hook. Override only the events you care about."""

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

   | Hook 方法 | 触发时机 | 此时 `session.tail` |
   |---|---|---|
   | `on_turn_start(session)` | §2.5 步骤 2 之前（追加 `UserPromptNode` 之前） | 上一轮链尾 |
   | `on_turn_end(session)` | §2.5 步骤 7.1（compress 判据评估之前），含成功 / 取消 / 异常路径 | 本轮链尾 |
   | `on_tool_call(session)` | §2.5 步骤 3.3 中 `ToolCallNode` 冻结后，且在创建 `ToolResultNode` 之前 | 刚冻结的 `ToolCallNode` |
   | `on_tool_result(session)` | §2.5 步骤 3.3 中 `ToolResultNode` 全部结果到位并冻结后 | 刚冻结的 `ToolResultNode` |
   | `on_compress(session)` | compress 任务（post-turn 异步或 in-turn retry）完成后，`session.tail` 已更新为新链头 | 新链头 |
   | `on_fork(source, forked)` | `Session.fork()` 成功创建新 session 后 | 不变 |
   | `on_cancel(session)` | turn 被取消、未完成节点已冻结后；随后 `on_turn_end` 仍会在 finally 中触发 | 已冻结的尾 |

3. 异常隔离：单个 hook 抛异常不阻断主流程；编排层对每次 hook 调用 `try/except`，异常以 ERROR 级别记入日志（含 hook 类名、`session_id`、`turn_id`），继续下一个 hook。
4. 多 hook 顺序：按配置顺序串行调用；不并发，避免对 `session.tail` 等共享状态产生竞争。
5. `SummaryNode` 不参与 hook 的"原始节点记录"语义——它是对事实的摘要，不是事实本身。需要记录原始节点的 hook（如 FileLogger）应跳过 `SummaryNode`；关心压缩事件的 hook 改用 `on_compress` 而不是从节点链里识别 `SummaryNode`。

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
2. 内部状态 `last_tail_ids: dict[str, str]`：session_id → 上次成功记录时的 `session.tail.id`。
3. 遍历算法：`on_turn_end` 触发时从 `session.tail` 向前回溯；遇 `id == last_tail_ids[session_id]` 停止（首次调用无 stop point，遍历整条链）；跳过 `SummaryNode`；按正序持久化；完成后更新 `last_tail_ids`。
4. Stop point 可达性：`on_turn_end` 在 compress 之前触发（§2.5 步骤 7.1），compress 至少保留 `keep_turns ≥ 1` 轮，所以上次 tail 始终在 preserve zone 内。
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
- 实现：子任务独立 `Session` 与主隔离；结果含 `output_text` / `stop_reason`；异常被捕获作 failed 返回；`inheritance=true` 时倒推到第一个非 frozen 节点 fork；每个 task 300s 超时；子任务 tool 集合排除 `task`。

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

由 §2.8 `SessionJSONLStore` plugin 的 `ToolProvider` 侧暴露，仅在顶层配置 `session_store:` 存在（或 web frontend 自动启用）时注册。配合「`SummaryNode` 作索引、`search_session` 作正文检索」分工：compressor 把旧 turn 压成 `SummaryNode` 后，AI 通过本工具按需取回原始内容。

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
  | `user_prompt` / `tool_call` / `tool_result` / `assistant_response` | query 对该类型节点文本做子串匹配 | 命中的单个节点 |

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
    tail: Node | None
    def get_turn_tool_map(self) -> ToolMap: ...


class Backend(Protocol):
    context_window: int

    def generate(
        self, session: BackendSession
    ) -> AsyncIterator[SessionUpdate | BackendTurnResult]: ...
```

约束：

1. `generate()` 先 yield 零到多个 `SessionUpdate`，最后 yield 一个 `BackendTurnResult`。
2. backend 接收 `BackendSession`，遍历 `tail` 链式历史，对每个节点调用 `node.to_anthropic()` / `node.to_openai()` 取得 provider 特定消息列表，并按需做整合（如 SummaryNode 链首提升、assistant/user 序列拼装）；同时把 `session.get_turn_tool_map()` 转换为后端工具定义。
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

下表的逐节点转换在 `Node.to_anthropic()` 上实现（§2.1 规则 7）；本节定义 backend 层负责的整合规则：SummaryNode 链首提升、消息序列拼装、assistant/user 交替约束。

| 节点 | 转换 |
|------|------|
| `UserPromptNode` | `{role: user, content: prompt}` |
| `AssistantResponseNode`（无后续 tool call）| `{role: assistant, content: [{type: text, text}]}` |
| `AssistantResponseNode` + `ToolCallNode`（相邻）| 合并为一条 assistant，content = text(可选) + tool_use 块 |
| `ToolCallNode`（无前置 text）| `{role: assistant, content: [{type: tool_use, id, name, input}, ...]}` |
| `ToolResultNode` | `{role: user, content: [{type: tool_result, tool_use_id, content}, ...]}` |
| `SummaryNode`（链首）| 提升为 `system` 参数，不进 messages（backend 层处理，节点方法默认返回 user 消息）|
| `SummaryNode`（链中）| `{role: user, content: summary_text}` |

约束：assistant 与 user message 严格交替；`ToolResultNode` 紧接 `ToolCallNode` 所在 assistant message 后。`AssistantResponseNode.thinking` 与 `ToolCallNode.thinking` 不参与 messages 回填，仅供前端 reload history 时还原 thinking bubble。

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
