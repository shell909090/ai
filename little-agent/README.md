# little-agent

A minimal agent system with CLI frontend.

## Introduction

little-agent is a lightweight, extensible agent framework designed for building conversational AI applications. It features:

- **Inverted chain architecture** for session history management
- **Protocol-based design** for easy extension of backends, frontends, and tools
- **Async/await** pattern with asyncio for concurrent operations
- **OpenAI backend** with function calling support
- **CLI frontend** with interactive loop

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd little-agent

# Install dependencies
make install

# Or install with dev dependencies
make dev
```

## Usage

Create a `config.yaml` file:

```yaml
backend:
  type: openai
  model: gpt-4
  api_key: "sk-your-api-key"          # direct key (takes priority)
  # api_key_env: OPENAI_API_KEY       # OR read from environment variable
  # base_url: https://api.openai.com/v1  # optional custom endpoint

logging:
  level: INFO

tools:
  providers: []
```

Set your OpenAI API key (if using `api_key_env`):

```bash
export OPENAI_API_KEY="your-api-key"
```

Run the CLI:

```bash
little-agent --config config.yaml
```

## Development

```bash
# Format code
make fmt

# Run linter
make lint

# Run tests
make test

# Run all checks
make fmt lint build test
```

## Architecture

The project follows a protocol-based architecture:

- `little_agent/agent/` - Core agent and session logic
- `little_agent/backends/` - LLM backend implementations
- `little_agent/frontends/` - User interface implementations
- `little_agent/tools/` - Tool providers and management

## Author

Shell Xu <shell909090@gmail.com>

## License

MIT License
