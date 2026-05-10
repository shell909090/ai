# little-agent

A lightweight, extensible agent framework for building conversational AI applications.

[中文说明](README.cn.md)

## Introduction

little-agent features:

- **Inverted chain architecture** for efficient session history management and compression
- **Protocol-based design** — backends, frontends, and tools are all swappable
- **Multiple LLM backends** — OpenAI-compatible APIs and Anthropic Claude
- **Multiple frontends** — interactive CLI, WebSocket (ACP), and HTTP/WebSocket (Web)
- **MCP tool support (planned)** — currently tools are loaded as Python modules via the `tools.providers` config
- **Permission system** — Chain of Responsibility: per-tool allow/deny rules with user prompt fallback
- **Memory** — persist and recall facts across sessions
- **Auto-compression** — automatically summarize history when context window fills up

## Installation

```bash
git clone <repository-url>
cd little-agent

# Install runtime dependencies
make install

# Install with dev dependencies
make dev
```

## Usage

### Minimal config (OpenAI)

```yaml
backends:
  primary:
    type: openai
    model: gpt-4o
    api_key: "sk-your-api-key"       # or omit and set OPENAI_API_KEY env var

frontend:
  type: cli                          # cli | web | acp
```

### Minimal config (Anthropic)

```yaml
backends:
  primary:
    type: anthropic
    model: claude-opus-4-5
    api_key: "sk-ant-..."            # or set ANTHROPIC_API_KEY env var
    system: "You are a helpful assistant."   # optional system prompt

frontend:
  type: cli
```

### Auto-compression

little-agent compresses conversation history automatically when the context window
fills up. **No configuration is required** — compression is on by default and uses
the primary backend.

When the ratio of `(input_tokens + output_tokens) / context_window` exceeds `agent.R`
(default 0.75), the oldest turns are summarised into `SummaryNode`s and the raw history
is discarded. The most recent `compressor.keep_turns` (default 3) turns are always
kept verbatim.

**Tuning compression:**

```yaml
agent:
  R: 0.75                            # trigger compression when context is 75% full (default 0.75)

compressor:
  keep_turns: 3                      # keep this many recent turns verbatim (default 3)
  compressed_window: 0.15            # discard old summaries beyond 20% of context_window (default 0.15)
```

**Using a dedicated, cheaper backend for compression** (optional — saves cost):

```yaml
backends:
  primary:
    type: openai
    model: gpt-4o
    api_key_env: OPENAI_API_KEY
  compressor:                        # if omitted, primary backend is used
    type: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY
```

**Disabling compression entirely:**

```yaml
compressor: false
```

### Full config example

```yaml
backends:
  primary:
    type: openai
    model: gpt-4o
    api_key_env: OPENAI_API_KEY      # read key from environment variable
    base_url: https://api.openai.com/v1   # optional; override for proxies or local models
    timeout: 60.0
    max_concurrency: 1
    context_window: 128000
  compressor:                        # optional; omit to reuse primary backend for compression
    type: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY

frontend:
  type: cli                          # cli | web | acp

agent:
  R: 0.75                             # compress when context exceeds this ratio (default 0.75)

compressor:
  keep_turns: 3                      # recent turns kept verbatim (default 3)
  compressed_window: 0.15             # max fraction of context_window used by summaries (default 0.15)
  # Set `compressor: false` to disable compression entirely.

permissions:                         # list of checkers, evaluated top-to-bottom
  - type: blackwhitelist             # blacklist wins over whitelist; no match → ask user
    blacklist:
      - "dangerous_tool"             # always denied
    whitelist:
      - "read_file"                  # always allowed without prompting
      - "list_dir"
  # To allow ALL tools without prompting:  - type: yesman
  # To prompt for EVERY tool (default):   omit permissions key or use []

memory:
  type: file
  path: memory.jsonl
  backend: primary                   # which backend to use for memory summarisation

tools:
  providers: []                      # Python module providers
  task_tool: true                    # set false to disable the built-in create_task tool

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

### Configuration reference

#### `backends.primary` / `backends.compressor`

Both `primary` and `compressor` share the same fields.  
`compressor` is optional — if omitted the primary backend is reused for compression.

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `type` | **yes** | — | `openai` or `anthropic` |
| `model` | **yes** | — | Model name, e.g. `gpt-4o`, `claude-opus-4-5` |
| `api_key` | one of | — | API key literal. Mutually exclusive with `api_key_env` |
| `api_key_env` | one of | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Environment variable holding the API key |
| `base_url` | no | provider default | Override API endpoint (proxies, local models, LiteLLM) |
| `timeout` | no | `60.0` | Request timeout in seconds |
| `max_concurrency` | no | `1` | Max simultaneous in-flight requests to this backend |
| `context_window` | no | `128000` | Token limit of the model; used to compute compression ratio |
| `system` | no | — | System prompt (**Anthropic only**) |
| `max_tokens` | no | `8192` | Max output tokens per request (**Anthropic only**) |

At least one of `api_key` or `api_key_env` must resolve to a non-empty value.

#### `agent`

| Field | Default | Description |
|-------|---------|-------------|
| `R` | `0.75` | Compression trigger ratio: compress when `total_tokens / context_window > R` |

#### `compressor`

Set `compressor: false` to disable compression entirely.

| Field | Default | Description |
|-------|---------|-------------|
| `keep_turns` | `3` | Number of most-recent user turns to keep verbatim (not summarised) |
| `compressed_window` | `0.15` | Discard old summary nodes when they exceed this fraction of `context_window` |

#### `frontend`

| Field | Default | Description |
|-------|---------|-------------|
| `type` | `cli` | `cli`, `web`, or `acp` |
| `host` | `127.0.0.1` | Bind address (**web only**) |
| `port` | `8080` | Bind port (**web only**) |

#### `permissions`

A list of checkers evaluated top-to-bottom. Omit or set to `[]` to prompt the user for every tool call.

| Checker type | Fields | Behaviour |
|--------------|--------|-----------|
| `blackwhitelist` | `blacklist`, `whitelist` (lists of tool name patterns, fnmatch) | Blacklist checked first; match → deny. Whitelist match → allow. No match → pass to next checker |
| `yesman` | — | Allow everything unconditionally |

#### `memory`

| Field | Default | Description |
|-------|---------|-------------|
| `type` | — | `file` (only supported type) |
| `path` | — | Path to the JSONL file storing memories |
| `backend` | `primary` | Which backend to use for memory summarisation |

#### `tools`

| Field | Default | Description |
|-------|---------|-------------|
| `providers` | `[]` | List of `{type: python, module: "my.module"}` entries; each module must expose `create_provider()` returning a `ToolProvider` |
| `task_tool` | `true` | Set `false` to disable the built-in `create_task` tool |

### Running

```bash
uv run python -m little_agent.main --config config.yaml

# Override log level at runtime
uv run python -m little_agent.main --config config.yaml --loglevel DEBUG
```

### CLI commands

| Command | Description |
|---------|-------------|
| `/new` | Start a new session |
| `/fork` | Fork the current session |
| `/save <path>` | Save session to file |
| `/load <path>` | Load session from file |
| `/list-tools` | List available tools |
| `/cancel` | Cancel the running turn |
| `/quit` or `/exit` | Exit |

## Development

```bash
make fmt          # format with ruff
make lint         # ruff check + mypy --strict
make build        # compile-check all .py files
make unittest     # run tests
make test         # tests + coverage report

make fmt lint build test   # run everything
```

## Architecture

```
little_agent/
  agent/          # AgentCore, SessionCore, node chain, compression, permissions
  backends/       # OpenAI and Anthropic streaming backends
  frontends/      # CLI, Web (HTTP+WebSocket), ACP (WebSocket)
  tools/          # BashTool, TaskTool, MCP tool manager
  memory.py       # file-based session memory
  main.py         # config loading and entry point
```

## Author

Shell Xu <shell909090@gmail.com>

## License

MIT License
