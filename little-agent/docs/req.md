# 需求文档

## 1. 背景

本项目目标是实现一个最精简的 Agent 系统，并以最小可运行版本（MVP）的方式逐步演进。

本期聚焦最小能力闭环：对话 + tools = agent。

## 2. 目标

实现一个可在命令行中运行的最小 Agent 系统，满足以下条件：

1. 用户可以通过 CLI/ACP/Web 与 Agent 进行多轮对话。
2. Agent 在对话过程中可以按需调用 tools。
3. tools 支持通过配置文件注册；本期所有已注册 tool 对 agent 可见（动态子集选择推迟，见 §4.4）。
4. 整个系统的交互过程在架构上与 ACP（Agent Client Protocol）等效对齐。
5. UI 与核心 Agent 逻辑解耦，CLI 只是 ACP Client 的一种实现。
6. 产品长期规划包含三个 Frontend：CLI、Web、ACP。

## 3. 范围

1. CLI 交互入口。
2. 为未来 `web` 与原生 `acp` frontend 预留统一接口边界。
3. 单进程内的 ACP 等效调用抽象。
4. 基础会话管理能力：创建会话并进行 prompt turn。
5. Tool 注册机制。
6. 为未来的运行时动态 tool 子集选择预留接口钩子。
7. 至少一种本地插件式 tool 注册方式：通过配置文件注册 Python 模块暴露的 tool。
8. 为未来扩展子进程方式注册 tool 预留设计空间。
9. 日志配置支持 `logging.config.dictConfig`：允许通过配置文件自定义日志格式、级别、处理器等。
10. Web UI
11. 高级权限系统
12. 高级记忆系统
13. 运行时动态 tool 子集选择
14. Backend streaming

## 4. 核心需求

### 4.1 Agent 基本能力

1. Agent 必须支持接收用户输入并返回文本回复。
2. Agent 必须支持在一次 prompt turn 中执行零次或多次 tool 调用。
3. Agent 必须在工具结果返回后继续完成本轮推理，直到本轮结束。
4. 会话压缩：长对话自动压缩历史消息，降低 token 消耗。
5. 权限系统：每次 tool 调用经过 Permission 决策；支持配置黑白名单规则，未命中时默认询问 Client（用户）；支持 yesman 模式（全部放行）。
6. 会话日志（session logger）：支持注入一个或多个 logger，将对话历史持久化为只写记录；内置 FileLogger，每节点追加一行 JSON，支持多 session 共存。

### 4.2 ACP 等效架构

1. 系统内部接口设计必须与 ACP 的核心过程 1:1 映射，而不是直接把 UI 和 Agent 主逻辑耦合在一起。
2. 即便运行在同一进程内，也应使用函数调用去模拟 ACP 的 request/response 与 notification 过程。
3. 至少需要覆盖以下 ACP 语义：
   - initialize
   - session/new
   - session/prompt
   - session/update
   - session/cancel
4. CLI 作为 Client 侧实现，不得直接绕过 ACP 等效层操作 Agent 内核。

### 4.3 Tool 注册

1. Tool 必须可注册。
2. Tool 注册方式本期采用配置文件驱动的插件式注册。
3. 配置文件注册的第一种实现方式为：加载指定 Python 模块中的导出函数。
4. 系统设计上应兼容未来扩展到“子进程暴露接口”的注册方式。
5. Tool 元数据与描述结构应尽量对齐 MCP Tool 定义。
6. 本期至少需要支持 MCP Tool 的核心字段：`name`、`description`、`inputSchema`。
7. 加载配置中仍需记录插件加载入口。

### 4.4 Tool 选择子集

运行时动态 tool 子集选择是后续版本目标，本期不实现。

1. 本期 Agent 对本轮可见全部已注册 tools。
2. 架构上需要为以下两种后续策略预留钩子：
   - 启动时通过配置文件开关 tool；
   - 运行时动态切换本轮可见 tool 子集。
3. 未被选中的 tools 必须对本轮推理不可见，避免工具迷失（适用于未来实现）。

### 4.5 Tools 要求

1. Tool call 参数显示：CLI 显示具体 tool 调用指令，过长时截断尾部并提示行数。
2. 内置 bash tool：允许 Agent 执行 shell 命令并返回输出。
3. Bash tool 扩展：支持自定义 `cwd`、`env` 和 `stdin` 参数。
4. Task tool：允许 Agent 创建子任务（子会话），独立执行并返回结果。
5. HTTP tool：允许 Agent 发送 HTTP 请求，返回状态码、响应头和 body；
6. Edit File tool：创建、全量覆写或局部编辑文件；支持字符串匹配替换和位置区间操作；文件不存在时可选自动创建。

### 4.6 CLI 要求

1. 用户可以在命令行中启动交互式会话。
2. 用户可以发送 prompt 并看到 Agent 回复。
3. 用户应能看到基本的 tool 调用过程或结果摘要。
4. 本期 CLI 只需满足最小可用，不追求复杂交互体验。
5. CLI 支持 `/exit`（与 `/quit` 等效）、`/cancel`（取消当前 turn）、`/new`（创建新 session）、`/fork`（从当前 session 分叉）、`/list-tools`（列出已注册 tools）、`/save <path>`（序列化 session 到文件）、`/load <path>`（从文件恢复 session）。
6. CLI 消息显示分离：模型回复的"思考"与"显示"内容分离输出，每条消息 strip 前后空白。
7. CLI 支持 readline：方向键召回历史指令、指令历史持久化、Tab 补全。

### 4.7 Backend 要求

1. Backend 性能计数：每次请求记录 input/output token、执行时间、缓存信息，通过 INFO 级别日志输出。
2. Backend 调用超时：API 调用应有超时控制，防止网络异常导致 session 挂死。
3. 多模型支持：配置支持多个 backend 定义，不同组件（如主对话、压缩）可使用不同模型。
4. 支持通过配置为 OpenAI backend 指定 base_url，以兼容 API 代理（如 LiteLLM）或本地模型。
5. 支持 Anthropic backend：使用原生流式 API，thinking/reasoning 内容与正文分离输出；支持 `system` prompt 和 `max_tokens` 独立配置。

### 4.8 Web UI 要求

1. 用户可以在 Web 界面中选择或创建会话，发送 prompt 并查看 Agent 的流式响应。
2. 发送 prompt 后，界面应自动滚动到新消息位置；Agent 响应流式输出期间，若用户处于底部则持续跟随滚动；用户主动向上翻阅时暂停自动滚动。
3. Agent 执行期间（从发送 prompt 到收到 `session/prompt_response`），界面应显示明确的加载中状态（如 spinner 或禁用输入），让用户清晰感知系统正在工作。
4. Agent 执行期间，用户可以点击取消按钮中断当前 turn（等价于 ACP `session/cancel`）；取消后界面恢复可输入状态，并显示已被取消的部分输出。
5. 界面展示 tool 调用的名称、参数摘要及返回结果，并区分 completed / failed / cancelled 状态。
6. 界面支持查看历史会话列表并恢复任意会话。

## 5. 非功能需求

### 5.1 可扩展性

1. 核心 Agent、ACP 适配层、CLI、Tool Registry 需要模块化分离。
2. 后续应可以在不重写 Agent 内核的前提下增加新的 UI。
3. 后续应可以增加新的 tool 插件加载方式。
4. 支持多 backend 配置，不同组件可使用不同模型。

### 5.2 可测试性

1. 核心流程必须可单元测试。
2. Tool 注册与 tool 过滤逻辑必须可单元测试。
3. ACP 等效调用流程必须可测试。

### 5.3 可维护性

1. 代码需遵循项目中的 Python 规范。
2. 关键模块职责要清晰，避免 UI、协议适配、业务逻辑混杂。
3. 日志系统需要支持调试模式开关。

## 6. 验收标准

1. 可以从 CLI 启动一个 Agent 会话。
2. 用户输入一个 prompt 后，系统能够完成一次 prompt turn。
3. Agent 可以调用配置中已注册的任一工具，并基于结果继续回复。
4. 未通过配置注册的工具，Agent 不可调用。
5. Tool 可以通过配置文件注册，无需改动核心代码即可新增至少一个工具。
6. CLI 不直接调用 Agent 内核私有实现，而是通过 ACP 等效接口完成交互。
