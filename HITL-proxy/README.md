# HITL-proxy

OpenAPI proxy service for AI Agent operations with Human-in-the-Loop approval. Provides AAAA (Authentication, Authorization, Auditing, Approval) as a middleware between AI agents and target APIs.

## Features

- **OpenAPI Spec Import** — import any OpenAPI 3.0 spec, auto-extract operations and dependencies
- **Hybrid Search** — FTS5 keyword search + vector semantic search (chromem-go, HNSW), merged with RRF; falls back to FTS5-only when no embedding API is configured
- **MCP SSE Server** — exposes `search_tools` and `call_api` as MCP tools
- **HITL Approval** — per-operationId approval rules, blocks agent requests until human approves/rejects via Web UI
- **Credential Isolation** — AES-GCM encrypted credential store, scheme-aware injection (Bearer/Basic/apiKey header|query|cookie), agents never see target API keys
- **Audit Logging** — full audit trail in SQLite
- **API Key Auth** — Bearer token authentication for MCP endpoints
- **CLI Bridge** — Python stdio-to-SSE bridge for agents that only support MCP stdio transport

## Quick Start

```bash
# Build
make build

# Copy and edit config
cp config.example.yaml config.yaml

# Set credential encryption key (32 bytes hex)
export HITL_CRED_KEY=$(openssl rand -hex 32)

# Run
./bin/hitl-proxy -config config.yaml
```

## Authentication

API keys are managed in the Web UI at `http://localhost:8080/admin/apikeys`. Create a key by entering an agent name; the UI displays the plaintext key once — save it immediately.

Pass the **plaintext** key when connecting:

- **Direct SSE**: `Authorization: Bearer <key>` header
- **CLI Bridge**: `--api-key <key>` flag

## Import an OpenAPI Spec

```bash
curl -X POST "http://localhost:8080/specs/import?name=github" \
  -H "Content-Type: application/json" \
  -d @github-openapi.json
```

## MCP Connection

Direct SSE connection (requires API key):
```
SSE endpoint: http://localhost:8080/mcp/sse
Header: Authorization: Bearer <api-key>
```

### CLI Bridge (for stdio-only agents)

The bridge is a Python package under `cmd/hitl-bridge/`. It requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

Install and run via uv:
```bash
cd cmd/hitl-bridge
uv sync
uv run hitl-bridge --url http://localhost:8080/mcp/sse --api-key <key>
```

Or install via pip:
```bash
cd cmd/hitl-bridge
pip install .
hitl-bridge --url http://localhost:8080/mcp/sse --api-key <key>
```

Agent MCP config (e.g. Claude Desktop):
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
Search available API operations by natural language query.

Parameters:
- `query` (string, required) — search query
- `limit` (number, optional) — max results (default 10)

### call_api
Call a target API operation with HITL approval support.

Parameters:
- `operation_id` (string, required) — the operationId to call
- `params` (object, optional) — path/query/body parameters
- `reason` (string, optional) — explanation for the API call

## Web UI

Open `http://localhost:8080/` to view and manage pending approval requests.

## Credentials

Credentials are stored per spec using OpenAPI security scheme names as keys. Set credentials via the Web UI or directly in the encrypted file:

```
specName → { "SchemeName": "secret-value" }
```

The scheme name must match the key in the spec's `components.securitySchemes`. Examples:

| Scheme type | Example config | Injected as |
|---|---|---|
| `http: bearer` | `{"BearerAuth": "ghp_token"}` | `Authorization: Bearer ghp_token` |
| `http: basic` | `{"BasicAuth": "user:pass"}` | `Authorization: Basic <base64>` |
| `apiKey in: header` | `{"ApiKeyHeader": "mytoken"}` | `X-API-Key: mytoken` |
| `apiKey in: query` | `{"ApiKeyQuery": "mytoken"}` | `?api_key=mytoken` |
| `apiKey in: cookie` | `{"ApiKeyCookie": "mytoken"}` | `Cookie: api_key=mytoken` |

Specs imported before this feature (no scheme definitions) fall back to injecting all credential entries as raw headers.

## Vector Search (optional)

When `OPENAI_BASE_URL` is set, semantic vector search is enabled alongside FTS5. Results from both are merged using Reciprocal Rank Fusion (RRF).

```bash
# Ollama (local)
export OPENAI_BASE_URL=http://localhost:11434
export OPENAI_API_KEY=""          # not required for Ollama

# OpenAI
export OPENAI_BASE_URL=https://api.openai.com
export OPENAI_API_KEY=sk-xxx
```

Configure the model and vector store path in `config.yaml`:

```yaml
embedding:
  model: "nomic-embed-text"       # Ollama; use "text-embedding-3-small" for OpenAI
vector:
  path: "vector.db"               # chromem-go persistence directory
```

When `OPENAI_BASE_URL` is not set, the proxy operates in FTS5-only mode with no behaviour change.

## Configuration

See `config.example.yaml`:

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

Environment variables:
- `HITL_CRED_KEY` — 64-char hex string (32 bytes) for AES-256-GCM credential encryption
- `HITL_ADMIN_PASSWORD` — password for the Web UI (HTTP Basic Auth, username `admin`)
- `OPENAI_BASE_URL` — base URL of an OpenAI-compatible embedding API (enables vector search)
- `OPENAI_API_KEY` — API key for the embedding API (optional for Ollama)

## Development

```bash
make fmt      # gofmt + goimports
make lint     # golangci-lint + ruff check
make test     # go test + pytest
make build    # build proxy (Go) + sync bridge (Python/uv)
```
