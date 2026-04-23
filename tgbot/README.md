# tgbot远程操作模型

`tgbot` 目前有两种工作模式，使用前建议先理解差异：

1. `ACP模式`：直接运行 `python3 tgbot.py acp`，由 `tgbot` 启动并维护 Telegram 与 ACP agent 之间的实时桥接。
2. `/loop模式`：由外部 agent 循环调用 `python3 tgbot.py get` 拉取消息，自行处理后再通过 `python3 tgbot.py send` 回传结果。

其中，`ACP模式` 是当前项目的主要模式，`/loop模式` 是兼容既有外部循环工作流的模式。

## loop模式

使用telegram bot远程操控claude code。方法是，配置使用tgbot.py工具，让本机命令行可以和特定的telegram user交互。然后编写tgbot.md指令，驱动这个脚本来获得消息，处理消息，回复消息。最后配置claude code的/loop，定期执行这个脚本。注意，由于本机console实际无人值守，所以没有人审批权限。因此，要么不使用工具，要么使用`--dangerously-skip-permissions`来跳过审批，要么配置--allowedTools去放行合适工具。一旦实际启用工具，/loop很可能会卡死。

启动方法：

1. 用`claude --dangerously-skip-permissions`启动agent。
2. 读一下tgbot.md，照着执行。

安全警告：

1. 本模式通常需要 `--dangerously-skip-permissions` 或等效放权配置。一旦telegram账号或telegram bot账号被盗，等同于机器完全受控。一旦AI理解出错，可能造成任意破坏。请理解这点，并视自己接受能力而用。
2. `allow_users` 是强信任白名单。白名单内的用户共享同一个后端 ACP session，可以在不同私聊/群聊里驱动同一个 agent；上下文会互相影响，回复也可能体现前一个管理员留下的状态。只有在 Owner 与协作者彼此知情并接受这种共享上下文模型时才应启用。
3. `~/.config/telegram/config.ini` 包含 Bot Token，使用前请至少执行 `chmod 640 ~/.config/telegram/config.ini`；若机器上存在其他非信任用户，使用 `chmod 600`。

# tgbot.py

Telegram Bot 命令行工具，支持收取和发送消息。纯标准库，零依赖。

## 配置

配置文件路径：`~/.config/telegram/config.ini`

```ini
[bot]
token = YOUR_BOT_TOKEN
chat_id = YOUR_CHAT_ID
allow_users = 12345678,87654321

[acp]
command = claude --acp
cwd = /home/user/project

[cron]
file = ~/.config/telegram/crontab.md
```

- `chat_id`：Bot owner 的 Telegram user ID。`get`/`send` 模式使用；`acp` 模式用于主动下行消息（权限请求、cron 回复）。
- `allow_users`：逗号分隔的 Telegram user ID 列表，允许向 `acp` 模式发送指令。未设置时默认只有 `chat_id` 对应用户可以交互。
- `[acp] cwd`：同时作为 agent 子进程的实际工作目录，以及 ACP `session/new` / `session/load` 里的 `cwd` 参数。可被 `python3 tgbot.py acp --cwd /path/to/project` 覆盖。

注意：bot 需要先收到用户的 `/start` 消息才能向该用户发送消息。

## 用法

### ACP 守护模式

将 Telegram 消息转发给 ACP 兼容的 agent（Claude Code、Codex、OpenCode 等），并将回复流式发回。

```bash
# 使用 config 中配置的后端
python3 tgbot.py acp

# 指定后端命令（覆盖 config）
python3 tgbot.py acp --agent-cmd "codex --acp"

# 恢复已有会话
python3 tgbot.py acp --session-id <UUID>

# 自动批准所有权限请求（无人值守模式）
python3 tgbot.py acp --yolo
```

**消息过滤**：只处理 `allow_users` 中用户发来的消息（未配置时仅 `chat_id`）。回复发往消息所在的 chat，支持私聊和群聊并存。console log 只记录发言人 ID、username 和 chat，不再输出消息正文：

```text
12:34:56 INFO ACP prompt from [12345678 @alice] chat=-1001234567890
```

**权限处理**：agent 请求工具权限时，bot 会向 `chat_id`（owner）发送 Telegram 消息列出选项，等待 owner 回复：
- `y` / `Y`：允许（选第一个 allow 选项）
- `n` / `N`：拒绝
- 数字（如 `1`、`2`）：选择对应选项编号

回复必须是以上格式。等待权限期间，bot 会先对新消息执行 `allow_users` 过滤，并最多缓冲 5 条合法 prompt，待当前权限请求结束后按顺序继续处理；若 owner 回了超出选项范围的数字，会收到格式提示。

**回复流式推送**：agent 的回复按行缓冲，收到换行时 edit 同一条 Telegram 消息，完成后去掉光标。超过 4000 字符时自动分成新消息继续。

**共享会话模型**：`allow_users` 里的所有管理员共享同一个 ACP session。这个模型是刻意设计的：它允许协作者在不同会话里接力操作同一个 agent，但也意味着上下文和工具状态不会按用户隔离。

**Slash Commands**：如果 ACP agent 在会话启动后通过 `available_commands_update` 暴露可用 `/commands`，bot 会在启动时调用 Telegram `setMyCommands` 自动注册兼容的命令名。这里的命令菜单表示当前 agent 暴露出的能力，不是静态写死的产品配置。

**会话日志**：`acp` 模式会把日志写到 `$XDG_STATE_HOME/tgbot/`；若未设置 `XDG_STATE_HOME`，则写到 `~/.local/state/tgbot/`。文件名为 `session-<SESSION_ID>.jsonl`，权限会收紧到仅当前用户可读写。日志内容包含入站 prompt、最终定型后的回复，以及命令注册事件；消息正文不再写入 console log。

### /loop 模式

`/loop` 模式下，`tgbot` 主要充当 Telegram 的收发桥，实际 agent 逻辑由外部循环控制。

典型流程：

1. 外部循环调用 `python3 tgbot.py get` 拉取新消息。
2. 外部 agent 自行解析消息并执行本地工作。
3. 外部循环通过 `python3 tgbot.py send` 把结果发回 Telegram。

### 获取消息

```bash
# 仅显示配置 chat_id 的消息
python3 tgbot.py get

# 显示所有 chat 的消息
python3 tgbot.py get --all

# JSON 格式输出
python3 tgbot.py get --json

# 组合使用
python3 tgbot.py get --all --json
```

默认模式下，来自配置 chat_id 的消息直接显示为 `sender: text`，其他 chat 的消息带 `[chat_id=xxx]` 前缀。不论是否显示，所有消息都会被消费（offset 推进）。

JSON 输出格式：

```json
[
  {
    "time": "2026-03-24T21:10:55+00:00",
    "chat_id": 50198021,
    "is_default_chat": true,
    "from": "shell",
    "text": "/start"
  }
]
```

### 发送消息

```bash
# 使用配置里的 chat_id
python3 tgbot.py send "hello"

# 指定 chat_id
python3 tgbot.py send -c 123456 "hello"
```

### Cron

在 `acp` 模式运行期间，可按计划定时向 agent 发送 prompt，结果回复到 `chat_id`。

cron 任务配置在 markdown 文件中（`[cron] file` 指定路径），格式：

```markdown
## 0 9 * * *
早上好，请检查服务器日志，总结需要关注的问题。

## 30 18 * * 1-5
工作日结束，请整理今天的工作日志。
```

- 二级标题（`## `）后跟标准 5 字段 cron 表达式（`分 时 日 月 周`，dow 0=周日）
- 标题后的段落即为发给 agent 的 prompt
- 精度为分钟级（取决于 getUpdates 轮询间隔，最大误差约 30 秒）

### 日志

通过 `-l` 控制日志级别，默认 WARNING。

```bash
python3 tgbot.py -l DEBUG get
python3 tgbot.py -l INFO send "hello"
python3 tgbot.py -l INFO acp
```

## 开发

运行时依旧保持标准库实现，但开发和质量检查流程使用 `uv` 与 `Makefile` 统一管理。

```bash
uv sync
make fmt
make lint
make build
make unittest
make test
```

直接运行脚本的方式保持不变：

```bash
python3 tgbot.py get
python3 tgbot.py send "hello"
python3 tgbot.py acp
```

# 作者

Copyright (c) 2026 Shell Xu <shell909090@gmail.com>

# 授权

MIT
