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
```

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

**配置文件**（`~/.config/telegram/config.ini`）新增 `[acp]` section：

```ini
[bot]
token = YOUR_BOT_TOKEN
chat_id = YOUR_CHAT_ID

[acp]
command = claude --acp
cwd = /home/user/project
```

**权限处理**：默认模式下，agent 请求工具权限时，bot 会向用户发送 Telegram 消息列出选项，等待用户回复：
- `y` / `Y`：允许（选第一个 allow 选项）
- `n` / `N`：拒绝
- 数字（如 `1`、`2`）：选择对应选项编号

回复必须是以上格式，其他内容会收到提示并继续等待。

**回复流式推送**：agent 的回复会实时 edit 同一条 Telegram 消息，完成后去掉光标。

### 日志

通过 `-l` 控制日志级别，默认 WARNING。

```bash
python3 tgbot.py -l DEBUG get
python3 tgbot.py -l INFO send "hello"
python3 tgbot.py -l INFO acp
```
