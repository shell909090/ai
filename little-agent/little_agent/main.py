"""Main entry point for little-agent CLI."""

import argparse
import asyncio
import importlib
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from little_agent.agent.core import AgentCore
from little_agent.backends.openai import OpenAIBackend
from little_agent.frontends.cli import CliClient
from little_agent.tools.manager import AggregatedToolManager
from little_agent.tools.protocol import ToolProvider

logger = logging.getLogger(__name__)


def setup_logging(level: str) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def load_config(path: Path) -> dict[str, Any]:
    """Load YAML configuration."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping")
    return data


def load_providers_from_config(config: dict[str, Any]) -> list[ToolProvider]:
    """Load tool providers from configuration."""
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


async def main() -> None:
    """Main async entry point."""
    parser = argparse.ArgumentParser(description="Little Agent CLI")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    config = load_config(args.config)

    log_level = "DEBUG" if args.debug else config.get("logging", {}).get("level", "INFO")
    setup_logging(log_level)

    tools = AggregatedToolManager()

    for provider in load_providers_from_config(config):
        tools.register(provider)

    backend_config = config.get("backend", {})
    backend_type = backend_config.get("type", "openai")
    if backend_type != "openai":
        raise ValueError(f"Unsupported backend type: {backend_type}")

    api_key_env = backend_config.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(f"Environment variable {api_key_env} not set")

    backend = OpenAIBackend(
        model=backend_config.get("model", "gpt-4"),
        api_key=api_key,
    )

    client = CliClient()
    agent = AgentCore(client=client, backend=backend, tools=tools)
    await client.run(agent)


def entrypoint() -> None:
    """Synchronous entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    entrypoint()
