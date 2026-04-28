"""Tool configuration loader."""

import importlib
import logging
from typing import Any

from .protocol import ToolProvider

logger = logging.getLogger(__name__)


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
