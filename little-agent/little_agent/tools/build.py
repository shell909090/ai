"""Factory functions for assembling ToolManager and MCP providers from config."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from little_agent.tools.manager import ToolManager

logger = logging.getLogger(__name__)

_TASK_PROVIDER_PATH = "little_agent.tools.task.TaskToolProvider"
_BASH_PROVIDER_PATH = "little_agent.tools.bash.BashToolProvider"


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


def build_tools(config: dict[str, Any]) -> tuple[ToolManager, bool]:
    """Build and register tool providers from config; returns (tools, task_tool_enabled)."""
    tools = ToolManager()
    providers, task_enabled = load_providers_from_config(config)
    for provider in providers:
        try:
            tools.register(provider)
        except (TypeError, ValueError) as e:
            logger.warning("Failed to register provider %s: %s", provider, e)
    return tools, task_enabled


def parse_mcp_configs(config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
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


async def start_mcp_providers(
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
