# Trello Kanban Agent

一个用 Trello 看板驱动 [opencode](https://opencode.ai/) session 的协调器。
人类用 Trello 卡片表达任务，协调器自动启动、监控并总结 opencode session。

**English:** [README.md](README.md)

## 概述

- **todo** 列表中的卡片在容量允许时自动被拾取。
- 协调器为每张卡启动一个 opencode session，将卡片描述作为初始 prompt 发送，并把进度 comment 写回 Trello。
- Session 结束后，协调器请求简短总结，并将卡片移到 **done**。
- 人类可以随时把卡片从 **doing** 拖走，协调器会 abort 对应 session。
- 标签控制路由：只有带 `proj:*` 标签的卡片才由协调器管理，无此标签的卡片保持不动。`model:*` 指定 opencode 模型。

## 环境要求

- Go 1.21+
- Trello 账号（API key + OAuth token）
- opencode server（`opencode serve`）

## 安装

```sh
git clone <repo>
cd kanban
make build
```

二进制文件输出到 `bin/kanband`。

## 配置

### `.env`（敏感信息，不进 git）

```
TRELLO_API_KEY=<your-api-key>
TRELLO_TOKEN=<your-oauth-token>
OPENCODE_SERVER_USERNAME=<username>
OPENCODE_SERVER_PASSWORD=<password>
```

### `config.yaml`（非敏感，进 git）

```yaml
trello:
  board_id: "<board-id>"
  lists:
    todo: "<list-id>"       # Trello list ID，todo 列
    doing: "<list-id>"      # Trello list ID，doing 列
    done: "<list-id>"       # Trello list ID，done 列
  labels:
    attention: "attention"  # 需要人工关注时添加的 label 名称

opencode:
  base_url: "http://127.0.0.1:8567"
  workdir: "/path/to/repo"    # opencode session 工作目录
  default_model:
    providerID: "opencode-go"
    modelID: "minimax-m3"
  allowed_models:
    - label: "model:sonnet"
      providerID: "anthropic"
      modelID: "claude-sonnet-4"

projects:
  allowed:
    - label: "proj:agent"
      name: "agent"

capacity:
  total: 3
  per_project: 1

timer:
  interval: 5s
  abort_timeout: 60s
  summary_timeout: 60s
```

## 项目钩子：`.kanban.yml`

每个项目仓库可以提供 `.kanban.yml` 来自定义 Trello 卡片如何转为 opencode prompt，以及任务生命周期中运行哪些脚本。文件不存在时，协调器使用内置默认 prompt，不运行任何钩子。

```yaml
prompt:
  # 可选。存在时完整替代内置 card 格式化。
  template: |
    Trello card: {{ .Card.Title }}
    Description:
    {{ .Card.Description }}

  # 可选。始终追加到最终 prompt 后面。
  addons:
    - "开始前确认 git 工作树干净。"
    - "结束前运行 lint 和 unittest，并修复错误。"

hooks:
  session_new:         # 创建 opencode session 前运行
    command: ["./scripts/kanban-session-new.sh"]
    timeout: 180s
  session_finish:      # summary comment 写完后运行；失败只加 attention
    command: ["./scripts/kanban-session-finish.sh"]
    timeout: 300s
  session_abort:       # abort 确认后运行；失败只加 attention
    command: ["./scripts/kanban-session-abort.sh"]
    timeout: 120s
```

### 钩子结果通道

钩子通过 **fd 3**（协调器创建的管道写端）返回结构化 JSON：

```sh
printf '{"workdir":"%s","comment":"Worktree ready."}\n' "$WORKTREE" >&3
```

fd 3 为空表示无结果。非零退出、超时、JSON 非法或 `workdir` 非绝对路径均视为钩子失败。

### 钩子环境变量

| 变量 | 值 |
|---|---|
| `KANBAN_EVENT` | `session_new` / `session_finish` / `session_abort` |
| `KANBAN_CARD_ID` | Trello card ID |
| `KANBAN_CARD_TITLE` | 卡片标题 |
| `KANBAN_CARD_URL` | 卡片 URL |
| `KANBAN_PROJECT` | 项目名称 |
| `KANBAN_PROJECT_LABEL` | `proj:*` 标签 |
| `KANBAN_MODEL_PROVIDER` | 模型 provider ID |
| `KANBAN_MODEL_NAME` | 模型 ID |
| `KANBAN_SESSION_ID` | Session ID（`session_new` 阶段为 `__pending__`） |
| `KANBAN_WORKDIR` | 工作目录 |
| `KANBAN_HOOK_RESULT_FD` | 固定为 `3` |

钩子的 stdout/stderr 只进入调试日志，不写入 Trello comment。

## 卡片标签

| 标签 | 含义 |
|---|---|
| `proj:NAME` | 将卡片标记为 AI 管理，并指定所属项目（用于容量计数）。没有此标签的卡片协调器不会触碰。 |
| `agent:NAME` | 选择已配置的 agent；无此标签时使用 `kanban.default_agent`。 |
| `model:NAME` | driver 级标签，例如 opencode 模型选择；协调器只透传，不校验。 |
| `attention` | 需要人工关注，在异常或超时时由协调器添加。 |

只有带 `proj:*` 标签的卡片才归协调器管理。没有 `proj:*` 标签的卡片无论在哪个列表，协调器均不移动、不写 comment、不占用容量。

`proj:*` 或 `agent:*` 等调度标签未知或有多个时，卡片移到 **done** 并加 `attention`，comment 说明原因。其他标签（包括 `model:*`）由选中的 agent driver 解释，不会触发协调器层面的拒绝。

## AI 看板控制

协调器提供本地 Control API，让 AI 助手可以查询和修改 Trello 卡片，而无需持有 Trello 凭证。API 使用 Bearer token 鉴权，仅监听本机地址。

在 `.env` 中添加（推荐——所有密钥集中管理）：
```
KANBAN_CONTROL_TOKEN=<随机密钥>
```

或导出为真实环境变量（适合 Docker/CI 部署）：
```sh
export KANBAN_CONTROL_TOKEN=<随机密钥>
```

在 `config.yaml` 中添加：
```yaml
control:
  token_env: KANBAN_CONTROL_TOKEN
```

在项目目录内使用 `scripts/kanbanctl.py`，协调器会根据当前目录推断项目。详见 [`scripts/SKILL.md`](scripts/SKILL.md)。

```sh
export KANBAN_CONTROL_URL=http://127.0.0.1:8087
export KANBAN_CONTROL_TOKEN=<同上>

# 查询看板
python3 scripts/kanbanctl.py list-cards --list todo

# 创建 todo（自动推断项目）
python3 scripts/kanbanctl.py add-todo --title "修复登录超时"

# 移动和写 comment
python3 scripts/kanbanctl.py move <card_id> --list done
python3 scripts/kanbanctl.py comment <card_id> --text "已在 commit abc123 修复。"
```

## 运行

```sh
# 使用 config.yaml 默认配置
./bin/kanband

# 覆盖轮询间隔和容量
./bin/kanband -poll 10s -max-total 5 -max-per-project 2

# 写日志到文件
./bin/kanband -log /var/log/kanband.log

# 自定义 HTTP 监听地址（/health 端点）
./bin/kanband -http 0.0.0.0:8087
```

Ctrl+C 或 SIGTERM 可以优雅停止。

## 健康检查

```sh
curl http://127.0.0.1:8087/health
# {"status":"ok"}
```

## 开发

```sh
make fmt        # 格式化代码
make lint       # go vet
make build      # 编译
make unittest   # 单元测试
make test       # 单元测试 + smoke test
```

覆盖率目标：总体 75%，各模块不低于 50%。

## 调度逻辑

每个 timer tick 按固定顺序执行四步：

1. **check session finish** — 轮询所有 session 的 finish 事件，处理正常完成、abort 确认和异常结束。
2. **reconcile doing** — 对比任务状态与 Trello doing 列表；对离开 doing 的卡发送 abort，对新进入的卡启动 session。
3. **check timeouts** — 检查 abort 和 summary 超时。
4. **promote todo** — 在容量允许的前提下，将 todo 中的卡片移入 doing。

## 作者

Shell.Xu

## 许可证

MIT
