# tgbot 需求文档

## 1. 项目目标

`tgbot` 是一个基于 Telegram Bot 的远程操控桥接工具，用于把 Telegram 消息转发给 ACP（Agent Client Protocol）兼容 agent，并把 agent 的回复再发回 Telegram。当前项目的主要目标是支持远程、无人值守、强信任协作场景下的 agent 操作。

## 2. 适用场景

1. Owner 需要通过 Telegram 私聊或群聊远程驱动本机 agent。
2. Owner 允许少量强信任协作者共同使用同一个后端 agent。
3. 运行环境通常无人值守，无法依赖本地交互式审批。
4. 项目强调零依赖、单文件、易部署，适合快速落地和脚本化运行。

项目当前支持两种工作模式：一种是配合 `/cron` 或外部循环，每分钟拉取一次新指令，执行后再通过脚本的 `send` 能力把结果发回 Telegram；另一种是直接运行 `acp` 守护模式，由 Telegram 与 ACP agent 保持实时桥接。

## 3. 功能需求

### 3.1 基础消息收发

1. 提供 `get` 子命令，从 Telegram `getUpdates` 拉取新消息。
2. `get` 默认只显示配置 `chat_id` 对应会话的消息。
3. `get --all` 可以显示所有 chat 的消息。
4. `get --json` 需要输出结构化 JSON，包含时间、chat_id、发送者和正文。
5. 提供 `send` 子命令，向默认 `chat_id` 或指定 `chat_id` 发送文本消息。

### 3.2 ACP 桥接守护模式

1. 提供 `acp` 子命令，启动 ACP agent 子进程。
2. 支持通过配置文件或 `--agent-cmd` 指定后端 agent 命令。
3. 支持通过 `--session-id` 恢复已有 ACP session。
4. 支持把 Telegram 收到的文本消息转为 ACP prompt。
5. 支持把 ACP 的最终回复返回到原消息所在 chat。
6. 支持按行流式编辑 Telegram 消息，减少长回复等待感。
7. 长回复超过 Telegram 单条消息长度限制时，必须自动分片继续发送。

### 3.3 权限请求处理

1. 当 ACP agent 发起 `session/request_permission` 时，bot 必须把权限选项发送给 owner。
2. owner 可以通过 `y`、`n` 或数字编号完成审批。
3. `--yolo` 模式下允许自动选择第一个 allow 类选项。
4. 审批期间，bot 仍需持续拉取 Telegram updates。
5. 审批期间，新消息必须先经过 `allow_users` 过滤。
6. 审批期间需要最多缓冲 5 条合法 prompt，待当前审批完成后按顺序继续执行。
7. 当缓冲队列已满时，bot 需要丢弃后续合法 prompt，并向对应 chat 发送“稍后重试”提示。

### 3.4 用户与会话模型

1. `allow_users` 表示强信任白名单。
2. 白名单用户都可以向同一个后端 ACP session 发送指令。
3. 多个管理员共享同一个 agent 上下文，这是刻意设计，不需要为不同管理员隔离会话状态。
4. 不同 chat 中的管理员可以接力驱动同一个 agent。
5. 允许群聊使用，但群聊消息必须满足“@bot”或“回复 bot 消息”才算有效输入。
6. 非 `allow_users` 的消息不能进入业务处理流程。

### 3.5 Slash Commands 同步

1. 如果 ACP agent 暴露 `available_commands_update`，bot 需要识别并提取可用命令。
2. Telegram 兼容的命令名需要自动注册到 bot 命令菜单。
3. 当命令集合变化时，需要同步更新 Telegram 命令菜单。
4. 当 agent 不再暴露命令时，需要删除 Telegram 菜单中的对应命令。
5. Telegram 命令菜单反映的是当前 agent 暴露能力，而不是静态产品菜单。

### 3.6 Cron 定时任务

1. `acp` 模式运行期间，支持读取 markdown 格式 cron 文件。
2. cron 文件用 `## <cron_expr>` 定义时间表达式，标题后的正文为 prompt。
3. 命中 cron 表达式时，bot 需要自动向当前 ACP session 发送 prompt。
4. cron 结果必须回复到 owner 的 `chat_id`。
5. 同一分钟内同一任务只能触发一次。

### 3.7 日志需求

1. console log 需要支持日志级别切换。
2. console log 不应记录消息正文，只记录必要元信息。
3. 会话日志需要单独写入 JSON Lines 文件。
4. 会话日志必须记录入站 prompt、最终定型回复、命令注册事件，以及缓冲/出队/丢弃事件。
5. 会话日志必须写到工程目录之外，避免误加入 Git。
6. 会话日志路径优先使用 `$XDG_STATE_HOME/tgbot/`，未设置时回退到 `~/.local/state/tgbot/`。
7. 日志目录权限应限制为仅当前用户可访问。

## 4. 配置需求

配置文件路径固定为 `~/.config/telegram/config.ini`，至少支持以下配置：

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

配置要求如下：

1. `[bot] token` 必填。
2. `[bot] chat_id` 对 `send` 和 `acp` 模式是必需配置。
3. `[bot] allow_users` 未设置时，默认仅允许 `chat_id` 对应用户交互。
4. `[acp] command` 可被 `--agent-cmd` 覆盖。
5. `[acp] cwd` 同时作为 agent 进程工作目录和 ACP session 的 `cwd` 参数。
6. `[cron] file` 可选，存在时才启用定时任务。

## 5. 非功能需求

1. 纯标准库实现，避免额外依赖。
2. 主程序保持单文件，便于部署和维护。
3. 需要兼容长期运行的守护模式。
4. 网络调用失败时需要具备基础重试能力。
5. 代码应使用 logging，而不是散落的 print 调试。
6. 项目文档需要明确其高风险、强信任、无人值守的使用前提。

## 6. 安全与风险约束

1. 系统默认面向强信任环境，不面向公开用户服务。
2. 一旦 Telegram 账号或 Bot Token 泄露，攻击者可能获得等同机器控制权的能力。
3. 由于共享 session 设计，管理员之间的上下文影响和状态串联属于接受的系统行为。
4. 会话日志虽然允许记录敏感内容，但不得落入 Git 仓库目录。
5. 运行前应确保配置文件权限足够严格，建议至少 `chmod 640`，高风险场景下使用 `chmod 600`。

## 7. 当前交付范围

当前版本应至少交付以下能力：

1. `get` / `send` / `acp` 三个子命令。
2. ACP session 创建、恢复、prompt 转发和回复回传。
3. Telegram 群聊寻址识别。
4. 权限审批与 `--yolo` 自动批准。
5. Slash commands 自动注册。
6. 审批期间合法消息过滤与最多 5 条缓冲。
7. XDG state 目录下的结构化会话日志。
8. markdown cron prompt 调度。
