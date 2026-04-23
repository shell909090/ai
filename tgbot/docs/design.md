# tgbot 设计文档

## 1. 设计目标

`tgbot` 采用单文件 Python 脚本实现 Telegram Bot 与 ACP agent 的桥接。设计优先级如下：

1. 保持纯标准库、零外部依赖。
2. 兼顾命令行单次调用与长期守护运行。
3. 明确强信任共享 session 模型，而不是多租户隔离模型。
4. 在不引入复杂状态存储的前提下，支持最小可用的审批期间消息缓冲。

## 2. 总体架构

当前系统由一个入口脚本 `tgbot.py` 组成，按职责可拆为 6 个层次：

1. **配置层**：读取 `~/.config/telegram/config.ini`。
2. **Telegram API 层**：封装 `getUpdates`、`sendMessage`、`editMessageText`、`setMyCommands` 等 HTTP 调用。
3. **ACP 会话层**：管理 ACP 子进程、JSON-RPC 请求、session 生命周期和流式消息接收。
4. **消息归一化层**：把 Telegram update 过滤并转换成统一 prompt 结构。
5. **守护调度层**：驱动主循环、权限审批、缓冲队列、cron 触发。
6. **日志层**：输出 console log 和 session JSONL 日志。

## 3. 关键数据流

### 3.1 普通 Telegram prompt 流

1. 主循环调用 Telegram `getUpdates` 拉取消息。
2. 每条 update 先经过 `_extract_prompt()`。
3. `_extract_prompt()` 负责 `allow_users` 过滤、群聊寻址判断、正文提取和 `@bot` 去除。
4. 合法消息交给 `handle_prompt()`。
5. `handle_prompt()` 先在 Telegram 发送占位消息 `⏳`。
6. `handle_prompt()` 调用 `AcpSession.prompt()` 把文本转为 ACP prompt。
7. ACP 返回内容按行触发 `on_chunk()`，不断 edit 同一条 Telegram 消息。
8. 会话完成后，把最终回复落入 session log，并把最后文本定型到 Telegram。

### 3.2 权限审批流

1. ACP agent 发送 `session/request_permission`。
2. `AcpSession.prompt()` 把权限请求回调给 `on_permission()`。
3. `on_permission()` 调用 `_handle_permission()`，向 owner 发送带选项的 Telegram 消息。
4. `_handle_permission()` 轮询 `getUpdates` 等待 owner 回复 `y`、`n` 或数字编号。
5. 若期间收到其他 update，则先调用 `buffer_prompt()`。
6. `buffer_prompt()` 只保留通过 `allow_users` 过滤后的合法 prompt，并放入 `pending_prompts`。
7. 审批完成后，`AcpSession.prompt()` 继续执行；主循环在下一轮优先消费 `pending_prompts`。

### 3.3 Cron 流

1. `cmd_acp()` 启动时读取 cron markdown 文件。
2. 主循环每轮检查当前分钟是否命中某个 cron 表达式。
3. 若命中且该分钟尚未执行，则直接调用 `handle_prompt()` 把 cron prompt 发给共享 session。
4. cron 回复统一发回 owner chat。

### 3.4 Slash Commands 同步流

1. ACP 在 session/update 中发送 `available_commands_update`。
2. `AcpSession._handle_session_update()` 提取 `availableCommands`。
3. `sync_telegram_commands()` 把 ACP command 名转换为 Telegram 兼容格式。
4. 通过 `setMyCommands` 或 `deleteMyCommands` 同步 Telegram 菜单。
5. 命令变更事件额外写入 session log。

## 4. 核心模块设计

### 4.1 配置与 Telegram API

- `load_config(path=CONFIG_PATH)`：加载配置文件并校验 `[bot]`、`token` 等必填项。
- `api_call(token, method, params=None, retries=0)`：统一封装 Telegram HTTP API 请求。

设计要点：

1. 所有 Telegram 访问都走 `api_call()`，便于统一日志与重试。
2. `HTTPError` 尽量解析 Telegram 返回体并交由上层判断。
3. 网络错误允许按调用方指定次数重试。

### 4.2 ACP 会话对象

`AcpSession` 封装 ACP 子进程和会话生命周期。

关键接口：

- `AcpSession.start(command, cwd, session_id=None, on_available_commands=None)`
- `AcpSession.prompt(text, on_chunk, on_permission)`
- `AcpSession.close()`

设计要点：

1. `start()` 同时负责 `initialize` 和 `session/new` / `session/load`。
2. agent 子进程真实工作目录使用传入的 `cwd`。
3. `prompt()` 使用后台线程消费 agent stdout，避免 Telegram API 调用阻塞 agent 输出。
4. `session/update` 中同时处理普通文本流、工具调用提示和命令更新。

### 4.3 消息归一化

`_extract_prompt(update, allow_users, bot_id, bot_username)` 把 Telegram update 归一为统一结构：

```python
{
  "text": str,
  "reply_chat_id": int,
  "source": "telegram",
  "from_id": int,
  "username": str,
  "chat_type": str,
  "message_id": int | None,
}
```

设计要点：

1. 这是所有 Telegram 输入的统一过滤入口。
2. 未通过 `allow_users` 的消息直接丢弃，不进入业务逻辑。
3. 群聊必须满足 reply 或 mention 才会被接受。
4. 群聊中的 `@bot` mention 会在进入 agent 前剥离。

### 4.4 Prompt 记录与回复输出

当前实现把 Telegram prompt 与 Telegram reply 各自收敛到统一 helper，减少主流程中的重复展开。

关键接口：

- `_prompt_record(...)`
- `_prompt_log_fields(prompt)`
- `TelegramReply`

设计要点：

1. prompt 的公共字段只由 `_prompt_record()` 构造，供正式处理、缓冲、出队和日志共用；
2. `_prompt_log_fields()` 只负责把统一 record 投影为日志字段，避免多处手工取值；
3. `TelegramReply` 负责占位消息、流式编辑、超长分片和最终定型，`handle_prompt()` 只保留 ACP 驱动逻辑；
4. 回复链路保持现有 Telegram 外部行为，不因内部拆分改变消息体验。

### 4.5 权限审批与缓冲队列

`_handle_permission()` 负责审批等待；`pending_prompts` 负责审批期间的合法消息缓冲。

关键设计：

1. 缓冲结构使用 `deque`，固定上限 `MAX_PENDING_PROMPTS = 5`。
2. 只缓冲通过 `_extract_prompt()` 的消息，避免无关用户干扰业务队列。
3. 队列满时直接丢弃新消息，并向发起方提示稍后重试。
4. 主循环优先消费缓冲队列，保证审批期间积压的合法消息按顺序执行。

该设计是“最小状态机”方案，不引入复杂的持久化队列或多级优先级。

### 4.6 会话日志

`SessionLog` 负责把结构化事件写入 JSONL。

日志目录策略：

1. 优先 `$XDG_STATE_HOME/tgbot/`
2. 回退 `~/.local/state/tgbot/`

当前记录的主要事件类型：

- `session_started`
- `commands_registered`
- `commands_cleared`
- `incoming_prompt`
- `outgoing_response`
- `prompt_buffered`
- `prompt_dequeued`
- `prompt_dropped`

安全设计：

1. 日志目录创建为 `0700`。
2. 日志文件创建/追加时尽量收紧到 `0600`。
3. 日志落盘位置与工程目录解耦，避免误提交到 Git。

### 4.7 内部编排与公共匹配逻辑

守护模式的高层编排集中在 `cmd_acp()`，但内部职责通过 helper 拆分，避免单函数持续膨胀。

关键设计：

1. mention 匹配通过公共 helper 提供统一的 UTF-16 区间扫描，供群聊寻址判断与 mention 剥离共享；
2. `cmd_acp()` 保留高层编排，配置解析、命令同步、缓冲出队、update 处理和 cron 调度交由内部 helper；
3. 外部 CLI 和 Telegram 交互行为保持稳定，重构只降低维护成本，不改变共享 session 与权限模型。

## 5. CLI 接口定义

当前命令行接口如下：

### 5.1 `get`

```bash
python3 tgbot.py get [-a|--all] [-j|--json]
```

行为：

1. 拉取 Telegram 新消息。
2. 默认仅显示配置 `chat_id` 的消息。
3. 所有拉取到的 updates 无论是否显示都会推进 offset。

### 5.2 `send`

```bash
python3 tgbot.py send [-c|--chat-id CHAT_ID] TEXT
```

行为：

1. 向默认或指定 chat 发送文本消息。

### 5.3 `acp`

```bash
python3 tgbot.py acp [--agent-cmd CMD] [--cwd DIR] [--session-id UUID] [--yolo]
```

行为：

1. 启动或恢复 ACP session。
2. 长期轮询 Telegram 并桥接消息。
3. 根据参数决定 agent 命令、工作目录、是否自动审批。

## 6. 共享信任模型

该项目不做多租户隔离，采用共享 session 设计：

1. `allow_users` 中的所有管理员拥有同级控制权。
2. 所有管理员共享同一个 agent 上下文、工具状态和命令菜单。
3. 一个管理员的 prompt 可能影响另一个管理员看到的后续结果。
4. 这是接受的产品行为，不是缺陷。

## 7. 当前限制

1. 项目没有持久化 offset，进程重启后依赖 Telegram 服务端未消费状态。
2. 缓冲队列只在内存中存在，进程退出后不会恢复。
3. `cmd_get` 与 `acp` 模式共用 Telegram updates，使用时需要避免互相抢占。
4. 当前仍是单文件主程序，后续若复杂度继续上升需要进一步模块化。
5. 当前实现只支持文本消息，不处理图片、附件、按钮回调等 Telegram 事件。

## 8. 后续演进方向

1. 如果复杂度继续增长，可把 Telegram API、ACP 会话、日志、cron 拆成独立模块。
2. 如需更可靠的无人值守运行，可增加 offset 持久化。
3. 如需更强审计控制，可为会话日志增加保留策略、裁剪和脱敏配置。
4. 如需更强协作隔离，可在未来改为每个管理员独立 ACP session，但这不属于当前需求范围。

## 9. 工程化与质量流程

项目运行时代码保持标准库实现，但开发流程采用 `uv` + `Makefile` 统一管理，避免脚本项目继续无序生长。

### 9.1 uv 环境定义

项目根目录使用 `pyproject.toml` 作为 `uv` 可识别的工程定义，承担两类职责：

1. 声明项目的基础元数据与 Python 版本范围；
2. 承载 `ruff` 与 `coverage` 的工具配置。

设计约束：

1. 运行时代码仍保持标准库实现，不新增运行时第三方依赖；
2. `uv run python tgbot.py ...` 与现有 `python3 tgbot.py ...` 均应可用；
3. 不把当前脚本强行拆包，只提供最小工程化元数据。

### 9.2 Makefile 质量入口

为匹配仓库规范，根目录 `Makefile` 统一暴露以下目标：

1. `make fmt`：执行格式化；
2. `make lint`：执行 `ruff check`，并启用 McCabe `max-complexity = 10`；
3. `make build`：执行 `python -m py_compile tgbot.py`；
4. `make unittest`：执行 `coverage run -m unittest discover`；
5. `make test`：在 `make unittest` 基础上输出覆盖率报告。

设计要点：

1. Python 解释器相关步骤通过 `uv run` 执行，`ruff` 和 `coverage` 复用本机已安装工具；
2. 若未来新增更多 Python 文件或测试模块，应保持入口不变，只扩展目标内部命令；
3. `fmt` 与 `lint` 分离，避免格式化副作用掩盖真实静态检查问题。

### 9.3 Ruff 配置

`ruff` 配置直接放入 `pyproject.toml`，避免引入额外配置文件。当前规则范围：

1. 启用 `E`、`F`、`I` 等基础规则，覆盖语法、未使用符号与导入顺序；
2. 启用 `C90` 并把 `max-complexity` 固定为 `10`；
3. 测试目录可按需放宽部分规则，但不放宽复杂度与明显错误类规则。

### 9.4 unittest 布局

当前 `tests/test_tgbot.py` 优先覆盖无需真实 Telegram/ACP 网络交互的逻辑，包括：

1. 群聊 mention 识别与剥离；
2. `_extract_prompt()` 的 `allow_users` 过滤与群聊判定；
3. cron markdown 解析；
4. prompt record / log field helper；
5. ACP 会话启动/流式处理、命令同步与命令行分发等可通过 mock 隔离的辅助逻辑。

设计约束：

1. 测试必须使用 `unittest` 与标准库 `unittest.mock`；
2. 不依赖真实 Telegram Token、网络访问或外部 ACP 进程；
3. 若需测试 `AcpSession` 或 Telegram API 交互，仅通过 mock 验证边界行为，不做真实集成。
