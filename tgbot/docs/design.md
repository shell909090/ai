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

### 4.4 权限审批与缓冲队列

`_handle_permission()` 负责审批等待；`pending_prompts` 负责审批期间的合法消息缓冲。

关键设计：

1. 缓冲结构使用 `deque`，固定上限 `MAX_PENDING_PROMPTS = 5`。
2. 只缓冲通过 `_extract_prompt()` 的消息，避免无关用户干扰业务队列。
3. 队列满时直接丢弃新消息，并向发起方提示稍后重试。
4. 主循环优先消费缓冲队列，保证审批期间积压的合法消息按顺序执行。

该设计是“最小状态机”方案，不引入复杂的持久化队列或多级优先级。

### 4.5 会话日志

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
4. 当前没有测试框架、Makefile 或多文件拆分，仍是脚本型项目。
5. 当前实现只支持文本消息，不处理图片、附件、按钮回调等 Telegram 事件。

## 8. 后续演进方向

1. 如果复杂度继续增长，可把 Telegram API、ACP 会话、日志、cron 拆成独立模块。
2. 如需更可靠的无人值守运行，可增加 offset 持久化。
3. 如需更强审计控制，可为会话日志增加保留策略、裁剪和脱敏配置。
4. 如需更强协作隔离，可在未来改为每个管理员独立 ACP session，但这不属于当前需求范围。
