"""Main entry point for little-agent CLI."""

import argparse
import asyncio
import importlib
import logging
import logging.config
import os
from pathlib import Path
from typing import Any

import yaml

from little_agent.agent.agent import AgentCore
from little_agent.backends.anthropic import AnthropicBackend
from little_agent.backends.openai import OpenAIBackend
from little_agent.frontends.acp import AcpClient
from little_agent.frontends.cli import CliClient
from little_agent.frontends.web import WebClient
from little_agent.tools.bash import BashToolProvider
from little_agent.tools.manager import ToolManager
from little_agent.tools.protocol import ToolProvider
from little_agent.tools.task import TaskToolProvider

logger = logging.getLogger(__name__)

_DEFAULT_LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "": {
            "level": "INFO",
            "handlers": ["console"],
        },
    },
}


def setup_logging(config: dict[str, Any] | None, level: str | None) -> None:
    """Configure logging from config or fallback to default config."""
    cfg = config if config is not None else _DEFAULT_LOGGING_CONFIG.copy()
    if level is not None:
        cfg.setdefault("loggers", {}).setdefault("", {})["level"] = level
    logging.config.dictConfig(cfg)


def load_config(path: Path) -> dict[str, Any]:
    """Load YAML configuration."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping")
    return data


def load_providers_from_config(config: dict[str, Any]) -> list[Any]:
    """Load tool providers from configuration."""
    providers: list[Any] = []
    tools_config = config.get("tools", {})
    provider_configs = tools_config.get("providers", [])

    for provider_config in provider_configs:
        provider_type = provider_config.get("type")
        if provider_type == "python":
            module_name = provider_config.get("module")
            if not module_name:
                logger.warning("Python provider missing 'module', skipping")
                continue
            try:
                module = importlib.import_module(module_name)
                provider = module.create_provider()
                if not isinstance(provider, ToolProvider) or isinstance(provider, (str, bytes)):
                    logger.warning("Provider from %s is not a ToolProvider, skipping", module_name)
                    continue
                providers.append(provider)
            except Exception:
                logger.exception("Failed to load python module provider: %s", module_name)
        else:
            logger.warning("Unknown provider type: %s", provider_type)

    return providers


def _build_backend(cfg: dict[str, Any], name: str) -> OpenAIBackend | AnthropicBackend:
    """Build a backend from a named backend config dict."""
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

    timeout_raw = cfg.get("timeout", 60.0)
    timeout = float(timeout_raw) if isinstance(timeout_raw, (int, float)) else 60.0

    max_concurrency = int(cfg.get("max_concurrency", 1))
    context_window = int(cfg.get("context_window", 128000))

    if backend_type == "anthropic":
        system: str | None = cfg.get("system") or None
        return AnthropicBackend(
            model=str(model),
            api_key=api_key,
            base_url=cfg.get("base_url"),
            timeout=timeout,
            max_concurrency=max_concurrency,
            context_window=context_window,
            system=system,
        )

    return OpenAIBackend(
        model=str(model),
        api_key=api_key,
        base_url=cfg.get("base_url"),
        timeout=timeout,
        max_concurrency=max_concurrency,
        context_window=context_window,
    )


def _load_tools(config: dict[str, Any]) -> ToolManager:
    """Load and register tool providers from config."""
    tools = ToolManager()
    providers = load_providers_from_config(config)
    providers.append(BashToolProvider())
    for provider in providers:
        try:
            tools.register(provider)
        except (TypeError, ValueError) as e:
            logger.warning("Failed to register provider %s: %s", provider, e)
    return tools


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
    """Load compressor if backends.compressor is configured."""
    compressor_cfg = backends_config.get("compressor")
    if not isinstance(compressor_cfg, dict):
        return None
    from little_agent.agent.compressor import LLMCompressor

    compressor_backend = _build_backend(compressor_cfg, "compressor")
    compressor_section = config.get("compressor") or {}
    keep_turns = int(compressor_section.get("keep_turns", 5))
    compressed_window = float(compressor_section.get("compressed_window", 0.2))
    compressed_window_tokens = int(compressed_window * primary_backend.context_window)
    return LLMCompressor(
        compressor_backend,
        keep_turns=keep_turns,
        compressed_window_tokens=compressed_window_tokens,
    )


def _load_permissions(config: dict[str, Any], client: Any) -> Any:
    """Build permission chain from config list, with client as terminal."""
    permissions_cfg = config.get("permissions")
    if isinstance(permissions_cfg, list):
        from little_agent.agent.permissions import build_permission_chain

        return build_permission_chain(permissions_cfg, client)
    return client


def _load_memory(config: dict[str, Any], backend: Any, backends_config: dict[str, Any]) -> Any:
    """Load memory system from config if present."""
    memory_cfg = config.get("memory")
    if isinstance(memory_cfg, dict):
        from little_agent.memory import FileMemory

        mem_type = memory_cfg.get("type", "file")
        if mem_type == "file":
            mem_path = memory_cfg.get("path", "memory.jsonl")
            mem_backend_name = memory_cfg.get("backend", "primary")
            mem_backend_cfg = backends_config.get(mem_backend_name)
            if isinstance(mem_backend_cfg, dict):
                mem_backend = _build_backend(mem_backend_cfg, mem_backend_name)
                return FileMemory(backend=mem_backend, path=mem_path)
            logger.warning("Memory backend '%s' not found, using primary", mem_backend_name)
            return FileMemory(backend=backend, path=mem_path)
    return None


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Little Agent CLI")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--loglevel", default=None, help="Override log level (DEBUG/INFO/WARNING/ERROR)"
    )
    args = parser.parse_args()

    config = load_config(args.config)

    log_config = config.get("logging")
    setup_logging(log_config, args.loglevel)

    tools = _load_tools(config)
    backend, backends_config = _load_backend(config)
    compressor = _load_compressor(config, backend, backends_config)
    memory = _load_memory(config, backend, backends_config)

    frontend_type = config.get("frontend", {}).get("type", "cli")

    if frontend_type == "web":
        client: CliClient | WebClient | AcpClient = WebClient()
    elif frontend_type == "acp":
        client = AcpClient()
    else:
        client = CliClient()

    permissions = _load_permissions(config, client)

    agent_cfg = config.get("agent") or {}
    compress_ratio = float(agent_cfg.get("R", 0.5))
    if not (0 < compress_ratio <= 1):
        raise ValueError(f"agent.R must be in range (0, 1], got {compress_ratio}")

    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=permissions,
        memory=memory,
        compress_ratio=compress_ratio,
        context_window=backend.context_window,
    )

    tools.register(TaskToolProvider(agent))

    asyncio.run(client.run(agent))


if __name__ == "__main__":
    main()
