# little-agent

一个极简的 Agent 系统，带有 CLI 前端。

## 简介

little-agent 是一个轻量级、可扩展的 Agent 框架，用于构建对话式 AI 应用。其特性包括：

- **倒链架构** 管理会话历史
- **基于协议的设计** 便于扩展后端、前端和工具
- **Async/await** 异步模式
- **OpenAI 后端** 支持函数调用
- **CLI 前端** 交互式循环

## 安装

```bash
# 克隆仓库
git clone <repository-url>
cd little-agent

# 安装依赖
make install

# 或安装开发依赖
make dev
```

## 使用

创建 `config.yaml` 文件：

```yaml
backend:
  type: openai
  model: gpt-4
  api_key_env: OPENAI_API_KEY

logging:
  level: INFO

tools:
  providers: []
```

设置 OpenAI API 密钥：

```bash
export OPENAI_API_KEY="your-api-key"
```

运行 CLI：

```bash
little-agent --config config.yaml
```

或直接运行：

```bash
python -m little_agent.main
```

## 开发

```bash
# 格式化代码
make fmt

# 运行静态检查
make lint

# 运行测试
make test

# 运行全部检查
make fmt lint build test
```

## 架构

项目采用基于协议的架构：

- `little_agent/agent/` - 核心 Agent 和会话逻辑
- `little_agent/backends/` - LLM 后端实现
- `little_agent/frontends/` - 用户界面实现
- `little_agent/tools/` - 工具提供者和管理

## 作者

Shell Xu <shell909090@gmail.com>

## 授权协议

MIT License
