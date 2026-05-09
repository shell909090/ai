# little-agent

A lightweight, extensible agent framework for building conversational AI applications.

[中文说明](README.cn.md)

## Introduction

little-agent features:

- **Inverted chain architecture** for efficient session history management and compression
- **Protocol-based design** — backends, frontends, and tools are all swappable
- **Multiple LLM backends** — OpenAI-compatible APIs and Anthropic Claude
- **Multiple frontends** — interactive CLI, WebSocket (ACP), and HTTP/WebSocket (Web)
- **MCP tool support** — connect external tool servers via Model Context Protocol
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

### Anthropic backend

```yaml
backends:
  primary:
    type: anthropic
    model: claude-opus-4-5
    api_key: "sk-ant-..."            # or set ANTHROPIC_API_KEY env var
    system: "You are a helpful assistant."   # optional system prompt
```

### Full config example

```yaml
backends:
  primary:
    type: openai
    model: gpt-4o
    api_key_env: OPENAI_API_KEY      # read key from environment variable
    base_url: https://api.openai.com/v1   # optional; override for proxies
    timeout: 60.0
    max_concurrency: 1
    context_window: 128000
  compressor:                        # separate backend used for compression
    type: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY

frontend:
  type: cli                          # cli | web | acp

agent:
  R: 0.7                             # compress when token ratio exceeds this (0 < R ≤ 1)

compressor:
  keep_turns: 5                      # keep this many recent turns verbatim
  compressed_window: 0.2             # target compressed size as fraction of context_window

permissions:                          # list of checkers, evaluated top-to-bottom
  - type: blackwhitelist             # blacklist wins over whitelist; no match → ask user
    blacklist:
      - "dangerous_tool"             # always denied
    whitelist:
      - "read_file"                  # always allowed without prompting
      - "list_dir"
  # tools not matched above are delegated to the user (prompted at runtime)
  #
  # To allow ALL tools without prompting (useful for automated/test runs):
  # permissions:
  #   - type: yesman
  #
  # To prompt for EVERY tool (default when permissions is omitted):
  # permissions: []   # or omit the key entirely

memory:
  type: file
  path: memory.jsonl
  backend: primary                   # which backend to use for memory summarisation

tools:
  providers: []                      # list of MCP server configs

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
