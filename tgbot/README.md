# tgbot远程操作模型

使用telegram bot远程操控claude code。方法是，配置使用tgbot.py工具，让本机命令行可以和特定的telegram user交互。然后编写tgbot.md指令，驱动这个脚本来获得消息，处理消息，回复消息。最后配置claude code的/loop，定期执行这个脚本。注意，由于本机console实际无人值守，所以没有人审批权限。因此，要么不使用工具，要么使用`--dangerously-skip-permissions`来跳过审批，要么配置--allowedTools去放行合适工具。一旦实际启用工具，/loop很可能会卡死。

启动方法：

1. 用`claude --dangerously-skip-permissions`启动agent。
2. 读一下tgbot.md，照着执行。

安全警告：

1. 本模式通常需要 `--dangerously-skip-permissions` 或等效放权配置。一旦telegram账号或telegram bot账号被盗，等同于机器完全受控。一旦AI理解出错，可能造成任意破坏。请理解这点，并视自己接受能力而用。
2. `chat_id` 必须填写你本人的 Telegram 用户 ID，只允许私聊，不得使用群组、频道或任何多人会话 ID；程序会消费全部 updates，但只有该私聊中的消息可作为指令来源。
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

注意：bot 需要先收到用户的 `/start` 消息才能向该用户发送消息。

## 用法

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

**消息过滤**：只处理 `allow_users` 中用户发来的消息（未配置时仅 `chat_id`）。回复发往消息所在的 chat，支持私聊和群聊并存。每条收到的指令会在日志中记录发言人 ID 和 username：

```
12:34:56 INFO ACP ← [12345678 @alice] 帮我查一下日志
```

**权限处理**：agent 请求工具权限时，bot 会向 `chat_id`（owner）发送 Telegram 消息列出选项，等待 owner 回复：
- `y` / `Y`：允许（选第一个 allow 选项）
- `n` / `N`：拒绝
- 数字（如 `1`、`2`）：选择对应选项编号

回复必须是以上格式，其他内容会收到提示并继续等待。

**回复流式推送**：agent 的回复按行缓冲，收到换行时 edit 同一条 Telegram 消息，完成后去掉光标。超过 4000 字符时自动分成新消息继续。

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
