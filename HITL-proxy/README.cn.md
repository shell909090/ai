# HITL-proxy

OpenAPI 代理服务，作为 AI Agent 操作第三方 API 的中间层，提供 AAAA（Authentication 认证、Authorization 授权、Auditing 审计、Approval 审批）能力。

## 功能特性

- **OpenAPI Spec 导入** — 导入任意 OpenAPI 3.0 规范，自动提取操作及依赖关系
- **混合检索** — FTS5 关键词检索 + 向量语义检索（chromem-go，HNSW 索引），RRF 融合排序；未配置 embedding API 时自动降级为纯 FTS5
- **MCP SSE 服务** — 对外暴露 `search_tools` 和 `call_api` 两个 MCP tool
- **HITL 审批** — 按 operationId 粒度配置审批规则，Agent 请求阻塞直至人工通过/拒绝
- **凭证隔离** — AES-GCM 加密凭证存储，按 OpenAPI security scheme 注入（Bearer/Basic/apiKey header|query|cookie），Agent 无法接触目标 API 密钥
- **审计日志** — 全量审计记录存储于 SQLite
- **API Key 认证** — MCP 端点的 Bearer token 认证
- **CLI 桥接** — Python 实现的 stdio 到 SSE 桥接工具，供仅支持 MCP stdio 传输的 Agent 使用

## 快速开始

```bash
# 构建
make build

# 复制并编辑配置
cp config.example.yaml config.yaml

# 设置凭证加密密钥（32 字节 hex）
export HITL_CRED_KEY=$(openssl rand -hex 32)

# 运行
./bin/hitl-proxy -config config.yaml
```

## 认证

API key 在 Web UI 的 `http://localhost:8080/admin/apikeys` 页面管理。填写 agent 名称后创建，明文 key 仅展示一次，请立即保存。

连接时传递**明文** key：

- **直连 SSE**：请求头 `Authorization: Bearer <key>`
- **CLI 桥接**：`--api-key <key>` 参数

## 导入 OpenAPI Spec

```bash
curl -X POST "http://localhost:8080/specs/import?name=github" \
  -H "Content-Type: application/json" \
  -d @github-openapi.json
```

## MCP 连接

直连 SSE（需要 API key）：
```
SSE 端点：http://localhost:8080/mcp/sse
请求头：Authorization: Bearer <api-key>
```

### CLI 桥接（适用于仅支持 stdio 的 Agent）

桥接工具位于 `cmd/hitl-bridge/`，使用 Python 实现，需要 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)。

通过 uv 安装运行：
```bash
cd cmd/hitl-bridge
uv sync
uv run hitl-bridge --url http://localhost:8080/mcp/sse --api-key <key>
```

或通过 pip 安装：
```bash
cd cmd/hitl-bridge
pip install .
hitl-bridge --url http://localhost:8080/mcp/sse --api-key <key>
```

Agent MCP 配置示例（以 Claude Desktop 为例）：
```json
{
  "mcpServers": {
    "hitl": {
      "command": "hitl-bridge",
      "args": ["--url", "https://proxy.example.com/mcp/sse", "--api-key", "sk-xxx"]
    }
  }
}
```

## MCP Tools

### search_tools
通过自然语言查询搜索可用的 API 操作。

参数：
- `query`（string，必填）— 搜索查询语句
- `limit`（number，可选）— 最大返回数量（默认 10）

### call_api
调用目标 API 操作，支持 HITL 审批。

参数：
- `operation_id`（string，必填）— 要调用的 operationId
- `params`（object，可选）— 路径参数、查询参数、请求体字段
- `reason`（string，可选）— 说明本次 API 调用的理由

## Web UI

打开 `http://localhost:8080/` 查看和管理待审批请求。

## 凭证管理

凭证按 spec 存储，以 OpenAPI security scheme 名称为 key。通过 Web UI 或直接修改加密文件配置：

```
specName → { "SchemeName": "secret-value" }
```

`SchemeName` 必须与 spec `components.securitySchemes` 中的键名一致，注入方式由 scheme 定义决定：

| Scheme 类型 | 配置示例 | 注入方式 |
|---|---|---|
| `http: bearer` | `{"BearerAuth": "ghp_token"}` | `Authorization: Bearer ghp_token` |
| `http: basic` | `{"BasicAuth": "user:pass"}` | `Authorization: Basic <base64>` |
| `apiKey in: header` | `{"ApiKeyHeader": "mytoken"}` | `X-API-Key: mytoken` |
| `apiKey in: query` | `{"ApiKeyQuery": "mytoken"}` | `?api_key=mytoken` |
| `apiKey in: cookie` | `{"ApiKeyCookie": "mytoken"}` | `Cookie: api_key=mytoken` |

在此功能上线前导入的 spec（无 scheme 定义）将回退为把所有凭证条目直接注入 header。

## 向量检索（可选）

设置 `OPENAI_BASE_URL` 后，语义向量检索将与 FTS5 并行运行，通过 RRF 融合结果。

```bash
# Ollama（本地）
export OPENAI_BASE_URL=http://localhost:11434
export OPENAI_API_KEY=""          # Ollama 不需要

# OpenAI
export OPENAI_BASE_URL=https://api.openai.com
export OPENAI_API_KEY=sk-xxx
```

在 `config.yaml` 中配置模型和向量库路径：

```yaml
embedding:
  model: "nomic-embed-text"       # Ollama 推荐；OpenAI 使用 "text-embedding-3-small"
vector:
  path: "vector.db"               # chromem-go 持久化目录
```

未设置 `OPENAI_BASE_URL` 时，代理在纯 FTS5 模式下运行，行为与之前完全一致。

## 配置

参见 `config.example.yaml`：

```yaml
listen: ":8080"
database:
  path: "hitl.db"
cred:
  file: "credentials.enc"
embedding:
  model: "text-embedding-3-small"
vector:
  path: "vector.db"
```

环境变量：
- `HITL_CRED_KEY` — 64 位 hex 字符串（32 字节），用于 AES-256-GCM 凭证加密
- `HITL_ADMIN_PASSWORD` — Web UI 密码（HTTP Basic Auth，用户名为 `admin`）
- `OPENAI_BASE_URL` — OpenAI-compatible embedding API 的 base URL（设置后启用向量检索）
- `OPENAI_API_KEY` — embedding API 的密钥（Ollama 不需要）

## 开发

```bash
make fmt      # gofmt + goimports
make lint     # golangci-lint + ruff check
make test     # go test + pytest
make build    # 构建 proxy (Go) + 同步 bridge (Python/uv)
```
