# HITL-proxy

OpenAPI proxy service for AI Agent operations with Human-in-the-Loop approval. Provides AAAA (Authentication, Authorization, Auditing, Approval) as a middleware between AI agents and target APIs.

## Features

- **OpenAPI Spec Import** — import any OpenAPI 3.0 spec, auto-extract operations and dependencies
- **FTS5 Search** — full-text search over API operations via `search_tools` MCP tool
- **MCP SSE Server** — exposes `search_tools` and `call_api` as MCP tools
- **HITL Approval** — per-operationId approval rules, blocks agent requests until human approves/rejects via Web UI
- **Credential Isolation** — AES-GCM encrypted credential store, agents never see target API keys
- **Audit Logging** — full audit trail in SQLite
- **CLI Bridge** — stdio-to-SSE bridge for agents that only support MCP stdio transport

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

## Import an OpenAPI Spec

```bash
curl -X POST "http://localhost:8080/specs/import?name=github" \
  -H "Content-Type: application/json" \
  -d @github-openapi.json
```

## MCP Connection

Direct SSE connection:
```
SSE endpoint: http://localhost:8080/mcp/sse
```

Via CLI bridge (for stdio-only agents):
```bash
./bin/hitl-bridge --url http://localhost:8080/mcp/sse
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
make lint     # golangci-lint
make test     # go test
make build    # build both binaries
```
