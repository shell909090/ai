"""Main entry point for little-agent CLI."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import logging.config
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_agent.agent.protocol import PermissionChecker

import yaml

from little_agent.agent.agent import AgentCore
from little_agent.backends.anthropic import AnthropicBackend
from little_agent.backends.openai import OpenAIBackend
from little_agent.frontends.acp import AcpClient
from little_agent.frontends.cli import CliClient
from little_agent.frontends.web import WebClient
from little_agent.tools.manager import ToolManager
from little_agent.tools.task import TaskToolProvider

logger = logging.getLogger(__name__)


class _ContextFilter(logging.Filter):
    """Inject session_id and turn_id from ContextVars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        from little_agent.agent.context import current_session_id, current_turn_id

        record.session_id = current_session_id.get("-")
        record.turn_id = current_turn_id.get("-")
        return True


def setup_logging(config: dict[str, Any], level: str | None) -> None:
    """Configure logging from the merged config dict."""
    if level is not None:
        config.setdefault("loggers", {}).setdefault("", {})["level"] = level
    logging.config.dictConfig(config)
    logging.getLogger().addFilter(_ContextFilter())


def load_config(path: Path) -> dict[str, Any]:
    """Load YAML configuration."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping")
    return data


_TASK_PROVIDER_PATH = "little_agent.tools.task.TaskToolProvider"
_BASH_PROVIDER_PATH = "little_agent.tools.bash.BashToolProvider"

_DEFAULT_CONFIG: dict[str, Any] = yaml.safe_load("""
tools:
  providers:
    little_agent.tools.bash.BashToolProvider:
      timeout: 30
      max_timeout: 1800
    little_agent.tools.task.TaskToolProvider: {}
agent:
  R: 0.75
compressor:
  keep_turns: 3
  compressed_window: 0.15
frontend:
  type: cli
logging:
  version: 1
  disable_existing_loggers: false
  formatters:
    default:
      format: "%(asctime)s [%(levelname)s] %(session_id).8s %(turn_id).8s %(name)s: %(message)s"
  handlers:
    console:
      class: logging.StreamHandler
      formatter: default
      stream: "ext://sys.stdout"
  loggers:
    "":
      level: INFO
      handlers: [console]
""")

_DEFAULT_BACKEND_CONFIG: dict[str, Any] = yaml.safe_load("""
timeout: 60.0
max_concurrency: 1
context_window: 128000
""")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict.

    override takes precedence including None values.
    When both values are dicts, merge recursively.
    base and override are not modified.
    """
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _validate_tools_config(tools_config: dict[str, Any]) -> None:
    """Raise ValueError for deprecated tools config fields."""
    if "task_tool" in tools_config:
        raise ValueError(
            "'tools.task_tool' is no longer supported. "
            "Enable task tool via: tools.providers: "
            "{little_agent.tools.task.TaskToolProvider: {}}"
        )
    if "bash" in tools_config and isinstance(tools_config.get("bash"), dict):
        raise ValueError(
            "'tools.bash.*' is no longer supported. "
            "Configure bash via: tools.providers: "
            "{little_agent.tools.bash.BashToolProvider: {timeout: 30}}"
        )
    providers_cfg = tools_config.get("providers")
    if providers_cfg is not None and not isinstance(providers_cfg, dict):
        raise ValueError(
            "'tools.providers' must be a dict mapping class paths to constructor args. "
            "Old list format is not supported. "
            "Example: tools.providers: {little_agent.tools.bash.BashToolProvider: {}}"
        )


def _import_provider(path: str, args: dict[str, Any]) -> Any:
    """Import and instantiate a provider class by dotted path."""
    module_path, _, class_name = path.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid provider class path: '{path}'")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(f"Cannot import provider '{path}': {e}") from e
    cls = getattr(mod, class_name, None)
    if cls is None:
        raise ImportError(f"Provider class not found: '{path}'")
    return cls(**args)


def load_providers_from_config(config: dict[str, Any]) -> tuple[list[Any], bool]:
    """Load tool providers from config dict; returns (providers, task_tool_enabled).

    Expects tools.providers to be a dict[class_path, constructor_args].
    Raises ValueError for old list-format or deprecated fields (task_tool, bash.*).
    TaskToolProvider is detected and excluded; caller must register it after agent creation.
    """
    tools_config = config.get("tools") or {}
    if not isinstance(tools_config, dict):
        tools_config = {}

    _validate_tools_config(tools_config)
    providers_cfg: dict[str, Any] = tools_config.get("providers") or {}

    task_enabled = False
    providers: list[Any] = []

    for path, args in providers_cfg.items():
        if args is None:
            continue  # explicit opt-out from default provider
        if not isinstance(args, dict):
            raise ValueError(
                f"Provider '{path}': constructor args must be a dict. "
                "Use {} for no-arg providers."
            )
        if path == _TASK_PROVIDER_PATH:
            task_enabled = True
            continue
        providers.append(_import_provider(path, args))

    return providers, task_enabled


def _build_backend(cfg: dict[str, Any], name: str) -> OpenAIBackend | AnthropicBackend:
    """Build a backend from a named backend config dict."""
    cfg = _deep_merge(_DEFAULT_BACKEND_CONFIG, cfg)
    backend_type = cfg.get("type")
    if not backend_type:
        raise ValueError(f"Backend '{name}' must contain a 'type' field")
    if backend_type not in ("openai", "anthropic"):
        raise ValueError(f"Unsupported backend type: {backend_type}")

    api_key: str | None = cfg.get("api_key")
    if not api_key:
        default_env = "ANTHROPIC_API_KEY" if backend_type == "anthropic" else "OPENAI_API_KEY"
        api_key_env: str = cfg.get("api_key_env", default_env)
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ValueError(
                f"No API key for backend '{name}': 'api_key' not set "
                f"and environment variable '{api_key_env}' not found"
            )

    model = cfg.get("model")
    if not model:
        raise ValueError(f"Backend '{name}' must contain a 'model' field")

    timeout = float(cfg["timeout"])
    max_concurrency = int(cfg["max_concurrency"])
    context_window = int(cfg["context_window"])

    if backend_type == "anthropic":
        system: str | None = cfg.get("system") or None
        max_tokens = int(cfg.get("max_tokens", 8192))
        return AnthropicBackend(
            model=str(model),
            api_key=api_key,
            base_url=cfg.get("base_url"),
            timeout=timeout,
            max_concurrency=max_concurrency,
            context_window=context_window,
            system=system,
            max_tokens=max_tokens,
        )

    return OpenAIBackend(
        model=str(model),
        api_key=api_key,
        base_url=cfg.get("base_url"),
        timeout=timeout,
        max_concurrency=max_concurrency,
        context_window=context_window,
    )


def _load_tools(config: dict[str, Any]) -> tuple[ToolManager, bool]:
    """Load and register tool providers from config; returns (tools, task_tool_enabled)."""
    tools = ToolManager()
    providers, task_enabled = load_providers_from_config(config)
    for provider in providers:
        try:
            tools.register(provider)
        except (TypeError, ValueError) as e:
            logger.warning("Failed to register provider %s: %s", provider, e)
    return tools, task_enabled


def _load_backend(config: dict[str, Any]) -> Any:
    """Load primary backend from config."""
    backends_config = config.get("backends")
    if not isinstance(backends_config, dict):
        raise ValueError("Config must contain a 'backends' section")
    if "primary" not in backends_config:
        raise ValueError("Config 'backends' must contain a 'primary' backend")

    primary_cfg = backends_config["primary"]
    if not isinstance(primary_cfg, dict):
        raise ValueError("Config 'backends.primary' must be a mapping")
    return _build_backend(primary_cfg, "primary"), backends_config


def _load_compressor(
    config: dict[str, Any], primary_backend: Any, backends_config: dict[str, Any]
) -> Any:
    """Load compressor, defaulting to primary backend when no dedicated backend is configured.

    Set ``compressor: false`` in config to disable compression entirely.
    """
    from little_agent.agent.compressor import LLMCompressor

    compressor_section = config.get("compressor")
    # Explicit opt-out.
    if compressor_section is False:
        return None

    if not isinstance(compressor_section, dict):
        compressor_section = _DEFAULT_CONFIG["compressor"]

    # Use a dedicated compressor backend if configured; otherwise fall back to primary.
    compressor_cfg = backends_config.get("compressor")
    compressor_backend = (
        _build_backend(compressor_cfg, "compressor")
        if isinstance(compressor_cfg, dict)
        else primary_backend
    )

    keep_turns = int(compressor_section["keep_turns"])
    compressed_window = float(compressor_section["compressed_window"])
    compressed_window_tokens = int(compressed_window * primary_backend.context_window)
    return LLMCompressor(
        compressor_backend,
        keep_turns=keep_turns,
        compressed_window_tokens=compressed_window_tokens,
    )


def _load_permissions(config: dict[str, Any], client: PermissionChecker) -> PermissionChecker:
    """Build permission chain from config list, with client as terminal."""
    permissions_cfg = config.get("permissions")
    if isinstance(permissions_cfg, dict):
        logger.warning(
            "permissions config is a dict (old format); ignored. "
            "Use a list of checkers: [{type: blackwhitelist, ...}]"
        )
        return client
    if isinstance(permissions_cfg, list):
        from little_agent.agent.permissions import build_permission_chain

        return build_permission_chain(permissions_cfg, client)
    return client


def _load_session_store(
    config: dict[str, Any],
    frontend_type: str,
    frontend_cfg: dict[str, Any],
) -> Any:
    """Load SessionJSONLStore from session_store: config, or auto-inject for web frontend."""
    from little_agent.agent.session_store import SessionJSONLStore

    session_store_cfg = config.get("session_store")
    if isinstance(session_store_cfg, dict):
        sessions_dir = str(
            session_store_cfg.get("sessions_dir", "~/.local/state/little_agent/sessions/")
        )
        filename_template = str(
            session_store_cfg.get("filename_template", "{session_id}_session.jsonl")
        )
        return SessionJSONLStore(sessions_dir=sessions_dir, filename_template=filename_template)
    elif session_store_cfg is None and frontend_type == "web":
        # Auto-inject for web frontend using the same sessions_dir as the web client.
        sessions_dir_raw = frontend_cfg.get("sessions_dir", "~/.local/state/little_agent/sessions/")
        store = SessionJSONLStore(sessions_dir=str(sessions_dir_raw))
        logger.info("session_store auto-enabled for web frontend")
        return store
    return None


def _load_hooks(config: dict[str, Any]) -> list[Any]:
    """Load hooks from config. Raises if loggers: key found (deprecated)."""
    if "loggers" in config:
        raise ValueError("Rename `loggers:` to `hooks:` or migrate to `session_store:`")
    hooks_cfg = config.get("hooks")
    if hooks_cfg is None:
        return []
    if not isinstance(hooks_cfg, list):
        logger.warning("hooks config is not a list; ignored")
        return []
    for item in hooks_cfg:
        if isinstance(item, dict):
            hook_type = item.get("type")
            raise ValueError(
                f"Unknown hook type: {hook_type!r}. "
                "No built-in hook types are registered via hooks:. "
                "Use session_store: for SessionJSONLStore."
            )
    return []


def _parse_mcp_provider_configs(config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Parse tools.mcp config into (name, cfg) pairs for async start."""
    tools_config = config.get("tools") or {}
    mcp_config = tools_config.get("mcp")
    if mcp_config is None:
        return []
    if not isinstance(mcp_config, dict):
        raise ValueError("'tools.mcp' must be a dict mapping server names to configs")
    result = []
    for name, cfg in mcp_config.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"MCP server '{name}': config must be a dict")
        command = cfg.get("command")
        if not isinstance(command, list):
            raise ValueError(
                f"MCP server '{name}': 'command' is required and must be a list of strings"
            )
        if not all(isinstance(c, str) for c in command):
            raise ValueError(f"MCP server '{name}': 'command' must be a list of strings")
        result.append((name, cfg))
    return result


async def _start_mcp_providers(
    mcp_cfgs: list[tuple[str, dict[str, Any]]],
    tools: ToolManager,
) -> list[Any]:
    """Instantiate and start MCP providers; register each on success."""
    from little_agent.tools.mcp import MCPStdioProvider

    providers: list[Any] = []
    for name, cfg in mcp_cfgs:
        provider = MCPStdioProvider(name=name, **cfg)
        try:
            await provider.start()
            tools.register(provider)
            providers.append(provider)
        except Exception:
            logger.exception("Failed to start MCP provider '%s'; it will not be available", name)
    return providers


async def _run_frontend_async(
    client: CliClient | WebClient | AcpClient,
    agent: AgentCore,
    config: dict[str, Any],
    frontend_type: str,
    initial_prompt: str | None,
) -> None:
    """Start and run the selected frontend."""
    if frontend_type == "web":
        from little_agent.frontends.web import WebClient as _WebClient

        cfg = config.get("frontend", {})
        if isinstance(client, _WebClient):
            host = cfg.get("host", "127.0.0.1") if isinstance(cfg, dict) else "127.0.0.1"
            port_raw = cfg.get("port", 8080) if isinstance(cfg, dict) else 8080
            port = int(port_raw) if isinstance(port_raw, (int, float)) else 8080
            await client.run(agent, host=str(host), port=port)
            return
    elif frontend_type == "cli":
        from little_agent.frontends.cli import CliClient as _CliClient

        if isinstance(client, _CliClient):
            await client.run(agent, initial_prompt=initial_prompt)
            return
    await client.run(agent)


async def _async_main(
    client: CliClient | WebClient | AcpClient,
    agent: AgentCore,
    tools: ToolManager,
    config: dict[str, Any],
    frontend_type: str,
    initial_prompt: str | None,
    mcp_cfgs: list[tuple[str, dict[str, Any]]],
) -> None:
    """Async entry: start MCP providers, run frontend, stop providers on exit."""
    mcp_providers = await _start_mcp_providers(mcp_cfgs, tools)
    try:
        await _run_frontend_async(client, agent, config, frontend_type, initial_prompt)
    finally:
        for provider in mcp_providers:
            try:
                await provider.stop()
            except Exception:
                logger.exception("Failed to stop MCP provider")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Little Agent CLI")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--loglevel", default=None, help="Override log level (DEBUG/INFO/WARNING/ERROR)"
    )
    parser.add_argument(
        "--prompt", default=None, help="Send an initial prompt automatically on startup (CLI only)"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    config = _deep_merge(_DEFAULT_CONFIG, config)

    setup_logging(config["logging"], args.loglevel)

    if "memory" in config:
        raise ValueError(
            "'memory:' config key is no longer supported. "
            "Use session_store: for session history search."
        )

    tools, task_enabled = _load_tools(config)
    backend, backends_config = _load_backend(config)
    compressor = _load_compressor(config, backend, backends_config)

    frontend_cfg = config.get("frontend") or {}
    frontend_type = str(frontend_cfg.get("type", "cli"))

    session_store = _load_session_store(config, frontend_type, frontend_cfg)
    hooks = _load_hooks(config)
    if session_store is not None:
        hooks.append(session_store)

    if frontend_type == "web":
        sessions_dir_raw = (
            frontend_cfg.get("sessions_dir") if isinstance(frontend_cfg, dict) else None
        )
        if sessions_dir_raw:
            sessions_dir: Path | None = Path(str(sessions_dir_raw)).expanduser()
        else:
            sessions_dir = Path("~/.local/state/little_agent/sessions").expanduser()
        client: CliClient | WebClient | AcpClient = WebClient(
            sessions_dir=sessions_dir, jsonl_store=session_store
        )
    elif frontend_type == "acp":
        client = AcpClient()
    else:
        client = CliClient()

    permissions = _load_permissions(config, client)

    compress_ratio = float(config["agent"]["R"])
    if not (0 < compress_ratio <= 1):
        raise ValueError(f"agent.R must be in range (0, 1], got {compress_ratio}")

    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=permissions,
        hooks=hooks,
        compress_ratio=compress_ratio,
        context_window=backend.context_window,
    )

    if session_store is not None:
        tools.register(session_store)

    if task_enabled:
        tools.register(TaskToolProvider(agent))

    mcp_cfgs = _parse_mcp_provider_configs(config)

    asyncio.run(_async_main(client, agent, tools, config, frontend_type, args.prompt, mcp_cfgs))


if __name__ == "__main__":
    main()
