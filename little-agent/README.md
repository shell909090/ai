# little-agent

A lightweight, extensible agent framework for building conversational AI applications.

[中文说明](README.cn.md)

## Introduction

little-agent features:

- **Inverted chain architecture** for efficient session history management and compression
- **Protocol-based design** — backends, frontends, and tools are all swappable
- **Multiple LLM backends** — OpenAI-compatible APIs and Anthropic Claude
- **Multiple frontends** — interactive CLI, WebSocket (ACP), and HTTP/WebSocket (Web)
- **MCP tool support (stdio)** — connect any MCP-compatible tool server via stdio transport (`tools.mcp` config)
- **Permission system** — Chain of Responsibility: per-tool allow/deny rules with user prompt fallback
- **Auto-compression** — automatically summarize history when context window fills up
- **Session search** — recall content from earlier turns that have been compressed

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
  compress_threshold: 0.75            # compress when context exceeds this ratio (default 0.75)

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

tools:
  providers:
    little_agent.tools.bash.BashToolProvider: {}
    little_agent.tools.task.TaskToolProvider: {}    # omit to disable
    little_agent.tools.http.HttpToolProvider: {}
    little_agent.tools.file.EditFileToolProvider: {}

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
| `compress_threshold` | `0.75` | Compression trigger ratio: compress when `total_tokens / context_window` exceeds this value |
| `max_tool_result_chars` | `50000` | Tool result size cap (serialised JSON characters); larger results are truncated |

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

#### `tools`

`tools.providers` is a dict mapping provider class paths to constructor args.
Omit a provider to disable it. Example with all built-in providers:

```yaml
tools:
  providers:
    little_agent.tools.bash.BashToolProvider:
      timeout: 30        # default command timeout (seconds)
      max_timeout: 1800  # per-call maximum
    little_agent.tools.task.TaskToolProvider: {}
    little_agent.tools.http.HttpToolProvider: {}
    little_agent.tools.file.EditFileToolProvider: {}
```

### Running

```bash
uv run python -m little_agent.main --config config.yaml

# Override log level at runtime
uv run python -m little_agent.main --config config.yaml --loglevel DEBUG

# One-shot CLI mode (send a single prompt, print the response, exit)
uv run python -m little_agent.main --config config.yaml --prompt "Hello, agent!"
```

The Makefile's `make run` target uses `~/.config/little_agent/config.yaml` as the
default config path. Pass `--config` explicitly when invoking the module to
override it.

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
make build        # build frontend + package into _static/ + py_compile check
make unittest     # run tests
make test         # tests + coverage report

make fmt lint build test   # run everything

# Frontend build is included in `make build` (npm ci + esbuild → _static/)
```

## Architecture

```
little_agent/
  types.py        # cross-package contracts: Agent / Session / Client / Hook /
                  # PermissionChecker / ToolRegistry / SessionUpdate + JSON primitives
  agent/          # AgentCore, SessionCore, node chain, compression, permissions,
                  # ToolManager (ToolRegistry impl), invoke_turn_tools, tool_setup (assembly)
  backends/       # OpenAI and Anthropic streaming backends
  frontends/      # CLI, Web (HTTP+WebSocket), ACP (WebSocket)
  tools/          # Pure tool implementations: BashTool, TaskTool, HttpTool, EditFileTool, MCP
  main.py         # config loading and entry point
```

Dependency direction: `main.py → frontends → agent → {tools, backends}`. All packages
import `types.py` for shared contracts; nothing in `types.py` imports a package at runtime.

`tools/` defines tool implementations and the `ToolProvider` protocol; it has no runtime
dependency on `agent/` (TaskTool is the lone exception — it spawns sub-agent sessions and
therefore touches agent internals). `agent/` owns the registry implementation (`ToolManager`),
the per-turn tool invocation pipeline, and the config-driven assembly logic (`tool_setup`).

## Security Notes

- **DEBUG logs may contain sensitive data**: When `--loglevel DEBUG` is active, backend
  request payloads are logged. Keys named `Authorization`, `Cookie`, `api_key`, `token`,
  or `secret` are automatically redacted, but the full conversation content is included.
  Use `INFO` log level in production environments.
- **`/save` files contain full history**: Session files written by `/save <path>` or the
  Web frontend contain the complete conversation history, including tool outputs. Treat
  them like sensitive data and restrict file permissions accordingly.

## Author

Shell Xu <shell909090@gmail.com>

## License

MIT License
