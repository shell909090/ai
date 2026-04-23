# tgbot Remote Operation Model

Chinese version: [README.cn.md](README.cn.md)

`tgbot` currently supports two working modes, and it is best to understand the difference before using it:

1. `ACP mode`: run `python3 tgbot.py acp` directly, and `tgbot` will start and maintain a live bridge between Telegram and an ACP agent.
2. `/loop mode`: an external agent loop calls `python3 tgbot.py get` to fetch messages, handles them on its own, and then sends results back through `python3 tgbot.py send`.

Among them, `ACP mode` is the main mode of the project, while `/loop mode` is the compatibility mode for existing external loop workflows.

## /loop Mode

Use a Telegram bot to remotely operate Claude Code. The basic method is to configure and use `tgbot.py` so the local command line can interact with a specific Telegram user. Then write instructions in `tgbot.md` so the script can fetch messages, process them, and send replies. Finally, configure Claude Code `/loop` to run this script periodically. Note that because the local console is effectively unattended, there is nobody available to approve permissions. In practice, that means either avoiding tools entirely, using `--dangerously-skip-permissions` to bypass approval, or configuring `--allowedTools` to allow an appropriate subset of tools. Once tools are actually enabled, `/loop` can easily get stuck.

Startup:

1. Start the agent with `claude --dangerously-skip-permissions`.
2. Read `tgbot.md` and follow it.

Security warnings:

1. This setup usually requires `--dangerously-skip-permissions` or an equivalent broad-permission configuration. If either the Telegram account or the Telegram bot account is compromised, the machine should be treated as fully compromised. If the AI misunderstands a request, it may also cause arbitrary damage. Please understand that risk before using it.
2. `allow_users` is a strong-trust whitelist. Users in the whitelist share the same backend ACP session and can drive the same agent from different private chats or groups. Context will affect each other, and replies may reflect state left behind by a previous administrator. This should only be enabled when the owner and collaborators know and accept the shared-context model.
3. `~/.config/telegram/config.ini` contains the bot token. Before use, run at least `chmod 640 ~/.config/telegram/config.ini`; if the machine has other untrusted local users, use `chmod 600`.

# tgbot.py

A Telegram bot command-line tool for receiving and sending messages. Standard-library only, with zero runtime dependencies.

## Configuration

Configuration file path: `~/.config/telegram/config.ini`

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

- `chat_id`: the Telegram user ID of the bot owner. Used by `get` and `send`; in `acp` mode it is also used for outbound messages such as permission prompts and cron replies.
- `allow_users`: a comma-separated list of Telegram user IDs allowed to send commands in `acp` mode. If unset, only the user identified by `chat_id` can interact.
- `[acp] cwd`: used both as the real working directory of the agent subprocess and as the `cwd` parameter in ACP `session/new` and `session/load`. It can be overridden with `python3 tgbot.py acp --cwd /path/to/project`.

Note: the bot must first receive `/start` from a user before it can send messages to that user.

## Usage

### ACP Daemon Mode

Forward Telegram messages to an ACP-compatible agent such as Claude Code, Codex, or OpenCode, and stream the replies back.

```bash
# Use the backend configured in config
python3 tgbot.py acp

# Specify the backend command and override config
python3 tgbot.py acp --agent-cmd "codex --acp"

# Resume an existing session
python3 tgbot.py acp --session-id <UUID>

# Automatically approve all permission requests (unattended mode)
python3 tgbot.py acp --yolo
```

**Message filtering**: only messages from users in `allow_users` are processed, or only `chat_id` if `allow_users` is not configured. Replies are sent back to the chat where the message came from, so private chats and groups can coexist. Console logs only record sender ID, username, and chat, and no longer print message bodies:

```text
12:34:56 INFO ACP prompt from [12345678 @alice] chat=-1001234567890
```

**Permission handling**: when the agent requests tool permission, the bot sends a Telegram message to `chat_id` (the owner) listing the options and waits for a reply:
- `y` / `Y`: allow, choosing the first allow option
- `n` / `N`: deny
- a number such as `1` or `2`: choose the corresponding option

Replies must use one of the formats above. While waiting for permission, the bot first filters new messages through `allow_users`, then buffers up to 5 valid prompts and continues processing them in order after the current permission request ends. If the owner replies with a number outside the option range, the bot sends a format reminder.

**Streaming replies**: agent replies are buffered by line. When a newline arrives, the bot edits the same Telegram message. When the response is complete, the cursor is removed. Replies longer than 4000 characters are automatically split into new messages.

**Shared session model**: all administrators in `allow_users` share the same ACP session. This is intentional: it allows collaborators to hand off work across different chats, but it also means context and tool state are not isolated per user.

**Slash commands**: if the ACP agent exposes available `/commands` through `available_commands_update` after the session starts, the bot automatically registers compatible command names with Telegram using `setMyCommands`. The command menu represents the capabilities currently exposed by the agent, not a statically defined product menu.

**Session log**: in `acp` mode, logs are written to `$XDG_STATE_HOME/tgbot/`; if `XDG_STATE_HOME` is not set, they are written to `~/.local/state/tgbot/`. The file name is `session-<SESSION_ID>.jsonl`, and permissions are tightened so only the current user can read and write it. The log contains inbound prompts, finalized replies, and command registration events; message bodies are no longer written to console logs.

### /loop Mode

In `/loop` mode, `tgbot` mainly acts as a Telegram send/receive bridge, while the actual agent logic is controlled by an external loop.

Typical flow:

1. The external loop calls `python3 tgbot.py get` to fetch new messages.
2. The external agent interprets the messages and performs local work.
3. The external loop sends the result back to Telegram with `python3 tgbot.py send`.

### Fetch Messages

```bash
# Show only messages from the configured chat_id
python3 tgbot.py get

# Show messages from all chats
python3 tgbot.py get --all

# Output JSON
python3 tgbot.py get --json

# Combine both
python3 tgbot.py get --all --json
```

In the default mode, messages from the configured `chat_id` are shown directly as `sender: text`, while messages from other chats include a `[chat_id=xxx]` prefix. Whether displayed or not, all messages are consumed because the offset advances.

JSON output format:

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

### Send Messages

```bash
# Use the configured chat_id
python3 tgbot.py send "hello"

# Specify a chat_id
python3 tgbot.py send -c 123456 "hello"
```

### Cron

While running in `acp` mode, the bot can send scheduled prompts to the agent and route the result back to `chat_id`.

Cron jobs are configured in a markdown file referenced by `[cron] file`, with this format:

```markdown
## 0 9 * * *
Good morning. Please check the server logs and summarize anything worth attention.

## 30 18 * * 1-5
At the end of the workday, please summarize today's work log.
```

- The level-2 heading (`## `) is followed by a standard 5-field cron expression (`minute hour day month weekday`, with Sunday as `0`)
- The paragraph below the heading becomes the prompt sent to the agent
- Precision is minute-level, depending on the `getUpdates` polling interval, with up to about 30 seconds of skew

### Logging

Use `-l` to control the log level. The default is `WARNING`.

```bash
python3 tgbot.py -l DEBUG get
python3 tgbot.py -l INFO send "hello"
python3 tgbot.py -l INFO acp
```

## Development

Runtime behavior still stays standard-library only, but development and quality checks are managed with `uv` and `Makefile`.

```bash
uv sync
make fmt
make lint
make build
make unittest
make test
```

Direct script usage remains unchanged:

```bash
python3 tgbot.py get
python3 tgbot.py send "hello"
python3 tgbot.py acp
```

# Author

Shell Xu <shell909090@gmail.com>

# Copyright

Copyright (c) 2026 Shell Xu

# License

MIT
