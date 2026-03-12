# HITL-proxy

OpenAPI 代理服务，作为 AI Agent 操作第三方 API 的中间层，提供 AAAA（Authentication 认证、Authorization 授权、Auditing 审计、Approval 审批）能力。

## 功能特性

- **OpenAPI Spec 导入** — 导入任意 OpenAPI 3.0 规范，自动提取操作及依赖关系
- **FTS5 全文搜索** — 通过 MCP tool `search_tools` 对 API 操作进行全文检索
- **MCP SSE 服务** — 对外暴露 `search_tools` 和 `call_api` 两个 MCP tool
- **HITL 审批** — 按 operationId 粒度配置审批规则，Agent 请求阻塞直至人工通过/拒绝
- **凭证隔离** — AES-GCM 加密凭证存储，Agent 无法接触目标 API 密钥
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

API key 以 SHA-256 哈希形式存储在 SQLite 的 `api_keys` 表中。目前没有管理 API，需要直接操作数据库创建 key：

```sql
-- 生成一个 key（例如 sk-mykey123），然后插入其 SHA-256 哈希
-- Linux/macOS：
echo -n "sk-mykey123" | sha256sum          -- 复制 hex 摘要

sqlite3 hitl.db "INSERT INTO api_keys (key_hash, label) VALUES ('<hex-摘要>', 'my key');"
```

连接时传递**明文** key：

- **直连 SSE**：请求头 `Authorization: Bearer sk-mykey123`
- **CLI 桥接**：`--api-key sk-mykey123` 参数

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

## 配置

参见 `config.example.yaml`：

```yaml
listen: ":8080"
database:
  path: "hitl.db"
cred:
  file: "credentials.enc"
```

环境变量：
- `HITL_CRED_KEY` — 64 位 hex 字符串（32 字节），用于 AES-256-GCM 凭证加密

## 开发

```bash
make fmt      # gofmt + goimports
make lint     # golangci-lint + ruff check
make test     # go test + pytest
make build    # 构建 proxy (Go) + 同步 bridge (Python/uv)
```
