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

from little_agent.agent.core import AgentCore
from little_agent.backends.openai import OpenAIBackend
from little_agent.frontends.cli import CliClient
from little_agent.tools.bash import BashToolProvider
from little_agent.tools.manager import ToolManager
from little_agent.tools.protocol import ToolProvider

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


def load_providers_from_config(config: dict[str, Any]) -> list[ToolProvider]:
    """Load tool providers from configuration.

    Note: ``isinstance(provider, ToolProvider)`` only checks that the object
    implements the required methods (``list`` and ``invoke``) due to
    ``@runtime_checkable``. It does **not** validate method signatures.
    """
    providers: list[ToolProvider] = []
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
                if not isinstance(provider, ToolProvider):
                    logger.warning("Module %s did not return a ToolProvider", module_name)
                    continue
                providers.append(provider)
            except Exception:
                logger.exception("Failed to load python module provider: %s", module_name)
        else:
            logger.warning("Unknown provider type: %s", provider_type)

    return providers


def _build_backend(cfg: dict[str, Any], name: str) -> OpenAIBackend:
    """Build an OpenAIBackend from a named backend config dict."""
    backend_type = cfg.get("type")
    if not backend_type:
        raise ValueError(f"Backend '{name}' must contain a 'type' field")
    if backend_type != "openai":
        raise ValueError(f"Unsupported backend type: {backend_type}")

    api_key: str | None = cfg.get("api_key")
    if not api_key:
        api_key_env: str = cfg.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ValueError(
                f"No API key for backend '{name}': 'api_key' not set "
                f"and environment variable '{api_key_env}' not found"
            )

    timeout_raw = cfg.get("timeout", 60.0)
    timeout = float(timeout_raw) if isinstance(timeout_raw, (int, float)) else 60.0

    return OpenAIBackend(
        model=cfg.get("model", "gpt-4"),
        api_key=api_key,
        base_url=cfg.get("base_url"),
        timeout=timeout,
    )


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

    tools = ToolManager()

    providers = load_providers_from_config(config)
    providers.append(BashToolProvider())
    for provider in providers:
        tools.register(provider)

    backends_config = config.get("backends")
    if not isinstance(backends_config, dict):
        raise ValueError("Config must contain a 'backends' section")
    if "primary" not in backends_config:
        raise ValueError("Config 'backends' must contain a 'primary' backend")

    primary_cfg = backends_config["primary"]
    if not isinstance(primary_cfg, dict):
        raise ValueError("Config 'backends.primary' must be a mapping")
    backend = _build_backend(primary_cfg, "primary")

    compressor_cfg = backends_config.get("compressor")
    compressor = None
    if isinstance(compressor_cfg, dict):
        from little_agent.compressor import LLMCompressor

        compressor_backend = _build_backend(compressor_cfg, "compressor")
        compressor = LLMCompressor(compressor_backend)

    client = CliClient()
    agent = AgentCore(client=client, backend=backend, tools=tools, compressor=compressor)

    from little_agent.tools.task import TaskToolProvider

    tools.register(TaskToolProvider(agent))

    asyncio.run(client.run(agent))


if __name__ == "__main__":
    main()
