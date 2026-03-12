# HITL-proxy

OpenAPI proxy service for AI Agent operations with Human-in-the-Loop approval. Provides AAAA (Authentication, Authorization, Auditing, Approval) as a middleware between AI agents and target APIs.

## Features

- **OpenAPI Spec Import** — import any OpenAPI 3.0 spec, auto-extract operations and dependencies
- **FTS5 Search** — full-text search over API operations via `search_tools` MCP tool
- **MCP SSE Server** — exposes `search_tools` and `call_api` as MCP tools
- **HITL Approval** — per-operationId approval rules, blocks agent requests until human approves/rejects via Web UI
- **Credential Isolation** — AES-GCM encrypted credential store, agents never see target API keys
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

API keys are stored as SHA-256 hashes in the SQLite `api_keys` table. There is no management API yet — create keys directly in the database:

```sql
-- Generate a key (e.g. sk-mykey123) and insert its SHA-256 hash
-- On Linux/macOS:
echo -n "sk-mykey123" | sha256sum          -- copy the hex digest

sqlite3 hitl.db "INSERT INTO api_keys (key_hash, agent_name) VALUES ('<hex-digest>', 'my-agent');"
```

Pass the **plaintext** key when connecting:

- **Direct SSE**: `Authorization: Bearer sk-mykey123` header
- **CLI Bridge**: `--api-key sk-mykey123` flag

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

## Configuration

See `config.example.yaml`:

```yaml
listen: ":8080"
database:
  path: "hitl.db"
cred:
  file: "credentials.enc"
```

Environment variables:
- `HITL_CRED_KEY` — 64-char hex string (32 bytes) for AES-256-GCM credential encryption

## Development

```bash
make fmt      # gofmt + goimports
make lint     # golangci-lint + ruff check
make test     # go test + pytest
make build    # build proxy (Go) + sync bridge (Python/uv)
```
