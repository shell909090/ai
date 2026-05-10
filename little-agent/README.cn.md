# little-agent

轻量级、可扩展的 Agent 框架，用于构建对话式 AI 应用。

[English](README.md)

## 简介

little-agent 的主要特性：

- **倒链架构** — 高效管理会话历史，支持自动压缩
- **基于协议的设计** — 后端、前端、工具均可独立替换
- **多 LLM 后端** — 支持 OpenAI 兼容 API 和 Anthropic Claude
- **多前端** — 交互式 CLI、WebSocket（ACP）、HTTP/WebSocket（Web）
- **MCP 工具支持（计划中）** — 当前工具通过 `tools.providers` 配置以 Python 模块方式加载
- **权限系统** — 责任链模式：对每个工具配置 allow/deny 策略，无匹配时自动询问用户
- **记忆** — 跨会话持久化并召回知识
- **自动压缩** — 上下文窗口接近上限时自动总结历史

## 安装

```bash
git clone <repository-url>
cd little-agent

# 安装运行时依赖
make install

# 安装开发依赖
make dev
```

## 使用

### 最简配置（OpenAI）

```yaml
backends:
  primary:
    type: openai
    model: gpt-4o
    api_key: "sk-your-api-key"       # 或省略，改设 OPENAI_API_KEY 环境变量

frontend:
  type: cli                          # cli | web | acp
```

### 最简配置（Anthropic）

```yaml
backends:
  primary:
    type: anthropic
    model: claude-opus-4-5
    api_key: "sk-ant-..."            # 或设置 ANTHROPIC_API_KEY 环境变量
    system: "You are a helpful assistant."   # 可选系统提示词

frontend:
  type: cli
```

### 自动压缩

little-agent 在上下文窗口接近上限时自动压缩会话历史。**无需任何配置**，压缩默认开启，使用主后端执行总结。

当 `(input_tokens + output_tokens) / context_window` 超过 `agent.R`（默认 0.75）时，最旧的若干轮次被总结为 `SummaryNode`，原始历史被丢弃。最近 `compressor.keep_turns`（默认 3）轮次始终完整保留。

**调整压缩参数：**

```yaml
agent:
  R: 0.75                            # 上下文占用率超过 70% 时触发压缩（默认 0.75）

compressor:
  keep_turns: 3                      # 保留最近若干轮完整历史（默认 3）
  compressed_window: 0.15            # 旧摘要总量超过 context_window 的 20% 时丢弃（默认 0.15）
```

**使用专用的低成本压缩后端（可选——节省费用）：**

```yaml
backends:
  primary:
    type: openai
    model: gpt-4o
    api_key_env: OPENAI_API_KEY
  compressor:                        # 省略时自动使用 primary 后端
    type: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY
```

**完全禁用压缩：**

```yaml
compressor: false
```

### 完整配置示例

```yaml
backends:
  primary:
    type: openai
    model: gpt-4o
    api_key_env: OPENAI_API_KEY      # 从环境变量读取密钥
    base_url: https://api.openai.com/v1   # 可选，用于代理或本地模型
    timeout: 60.0
    max_concurrency: 1
    context_window: 128000
  compressor:                        # 可选；省略时复用 primary 后端进行压缩
    type: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY

frontend:
  type: cli                          # cli | web | acp

agent:
  R: 0.75                            # 上下文占用率超过该值时触发压缩（默认 0.75）

compressor:
  keep_turns: 3                      # 保留最近若干轮完整历史（默认 3）
  compressed_window: 0.15            # 旧摘要总量上限，占 context_window 的比例（默认 0.15）
  # 设置 compressor: false 可完全禁用压缩。

permissions:                         # 检查器列表，从上到下依次执行
  - type: blackwhitelist             # 黑名单优先于白名单；无匹配则询问用户
    blacklist:
      - "dangerous_tool"             # 始终拒绝
    whitelist:
      - "read_file"                  # 始终放行，不询问
      - "list_dir"
  # 放行所有工具：  - type: yesman
  # 每次均询问（默认）：省略 permissions 字段或设为 []

memory:
  type: file
  path: memory.jsonl
  backend: primary                   # 用于记忆总结的后端

tools:
  providers: []                      # Python 模块工具列表
  task_tool: true                    # 设为 false 可禁用内置 create_task 工具

logging:
  version: 1
  disable_existing_loggers: false
  formatters:
    default:
      format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  handlers:
    console:
      class: logging.StreamHandler
      formatter: default
      stream: ext://sys.stdout
  loggers:
    "":
      level: INFO
      handlers: [console]
```

### 配置参考

#### `backends.primary` / `backends.compressor`

`primary` 和 `compressor` 使用相同的字段。  
`compressor` 为可选——省略时直接复用 primary 后端执行压缩。

| 字段 | 是否必填 | 默认值 | 说明 |
|------|----------|--------|------|
| `type` | **必填** | — | `openai` 或 `anthropic` |
| `model` | **必填** | — | 模型名称，如 `gpt-4o`、`claude-opus-4-5` |
| `api_key` | 二选一 | — | 直接填写 API Key，与 `api_key_env` 互斥 |
| `api_key_env` | 二选一 | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | 存放 API Key 的环境变量名 |
| `base_url` | 否 | 各厂商默认地址 | 覆盖 API 端点（代理、本地模型、LiteLLM） |
| `timeout` | 否 | `60.0` | 请求超时时间（秒） |
| `max_concurrency` | 否 | `1` | 该后端最大并发请求数 |
| `context_window` | 否 | `128000` | 模型 token 上限，用于计算压缩触发比例 |
| `system` | 否 | — | 系统提示词（**仅 Anthropic**） |
| `max_tokens` | 否 | `8192` | 单次请求最大输出 token 数（**仅 Anthropic**） |

`api_key` 与 `api_key_env` 至少有一个能解析到非空值。

#### `agent`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `R` | `0.75` | 压缩触发比例：`total_tokens / context_window > R` 时触发压缩 |

#### `compressor`

设置 `compressor: false` 可完全禁用压缩。

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `keep_turns` | `3` | 最近若干轮完整保留，不参与压缩 |
| `compressed_window` | `0.15` | 旧摘要节点总量超过 `context_window` 的该比例时开始丢弃 |

#### `frontend`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `type` | `cli` | `cli`、`web` 或 `acp` |
| `host` | `127.0.0.1` | 监听地址（**仅 web**） |
| `port` | `8080` | 监听端口（**仅 web**） |

#### `permissions`

检查器列表，从上到下依次执行。省略或设为 `[]` 表示每次工具调用均询问用户。

| 类型 | 字段 | 行为 |
|------|------|------|
| `blackwhitelist` | `blacklist`、`whitelist`（工具名称模式列表，支持 fnmatch） | 黑名单优先；命中黑名单 → 拒绝；命中白名单 → 放行；无匹配 → 交给下一个检查器 |
| `yesman` | — | 无条件放行所有工具 |

#### `memory`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `type` | — | `file`（当前唯一支持的类型） |
| `path` | — | 存储记忆的 JSONL 文件路径 |
| `backend` | `primary` | 用于记忆总结的后端名称 |

#### `tools`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `providers` | `[]` | Python 模块提供者列表，每项格式为 `{type: python, module: "my.module"}`；模块须暴露 `create_provider()` 方法 |
| `task_tool` | `true` | 设为 `false` 可禁用内置 `create_task` 工具 |

### 运行

```bash
uv run python -m little_agent.main --config config.yaml

# 临时覆盖日志级别
uv run python -m little_agent.main --config config.yaml --loglevel DEBUG

# 一次性模式（发送单个 prompt，打印回复后退出）
uv run python -m little_agent.main --config config.yaml --prompt "你好"
```

Makefile 的 `make run` 默认使用 `~/.config/little_agent/config.yaml` 作为配置路径，
直接以模块方式启动时通过 `--config` 显式指定即可覆盖。

### CLI 命令

| 命令 | 说明 |
|------|------|
| `/new` | 开始新会话 |
| `/fork` | 分叉当前会话 |
| `/save <路径>` | 保存会话到文件 |
| `/load <路径>` | 从文件加载会话 |
| `/list-tools` | 列出可用工具 |
| `/cancel` | 取消正在运行的轮次 |
| `/quit` 或 `/exit` | 退出 |

## 开发

```bash
make fmt          # 使用 ruff 格式化
make lint         # ruff 检查 + mypy --strict
make build        # 编译检查所有 .py 文件
make unittest     # 运行测试
make test         # 测试 + 覆盖率报告

make fmt lint build test   # 一键全部执行
```

## 架构

```
little_agent/
  agent/          # AgentCore、SessionCore、节点链、压缩、权限系统
  backends/       # OpenAI 和 Anthropic 流式后端
  frontends/      # CLI、Web（HTTP+WebSocket）、ACP（WebSocket）
  tools/          # BashTool、TaskTool、MCP 工具管理
  memory.py       # 基于文件的会话记忆
  main.py         # 配置加载与入口
```

## 作者

Shell Xu <shell909090@gmail.com>

## 授权协议

MIT License
