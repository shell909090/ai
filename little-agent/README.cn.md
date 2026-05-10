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

### Anthropic 后端

```yaml
backends:
  primary:
    type: anthropic
    model: claude-opus-4-5
    api_key: "sk-ant-..."            # 或设置 ANTHROPIC_API_KEY 环境变量
    system: "You are a helpful assistant."   # 可选系统提示词
```

### 完整配置示例

```yaml
backends:
  primary:
    type: openai
    model: gpt-4o
    api_key_env: OPENAI_API_KEY      # 从环境变量读取密钥
    base_url: https://api.openai.com/v1   # 可选，代理时覆盖
    timeout: 60.0
    max_concurrency: 1
    context_window: 128000
  compressor:                        # 压缩专用后端（可选）
    type: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY

frontend:
  type: cli                          # cli | web | acp

agent:
  R: 0.7                             # token 占用率超过该值时触发压缩（0 < R ≤ 1）

compressor:
  keep_turns: 5                      # 保留最近若干轮不压缩
  compressed_window: 0.2             # 压缩目标大小占 context_window 的比例

permissions:                          # 检查器列表，从上到下依次执行
  - type: blackwhitelist             # 黑名单优先于白名单；无匹配则询问用户
    blacklist:
      - "dangerous_tool"             # 始终拒绝
    whitelist:
      - "read_file"                  # 始终放行，不询问
      - "list_dir"
  # 未匹配的工具转交用户决定（运行时弹出提示）
  #
  # 放行所有工具（适合自动化测试）：
  # permissions:
  #   - type: yesman
  #
  # 每次均询问用户（省略 permissions 时的默认行为）：
  # permissions: []   # 或直接不写该字段

memory:
  type: file
  path: memory.jsonl
  backend: primary                   # 用于记忆总结的后端

tools:
  providers: []                      # MCP 服务器配置列表

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

### 运行

```bash
uv run python -m little_agent.main --config config.yaml

# 临时覆盖日志级别
uv run python -m little_agent.main --config config.yaml --loglevel DEBUG
```

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
