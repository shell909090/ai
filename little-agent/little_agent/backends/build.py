"""Factory functions for assembling backend and compressor instances from config."""

from __future__ import annotations

import os
from typing import Any

import yaml

from little_agent._utils import _deep_merge
from little_agent.backends.anthropic import AnthropicBackend
from little_agent.backends.openai import OpenAIBackend

_DEFAULT_BACKEND_CONFIG: dict[str, Any] = yaml.safe_load("""
timeout: 60.0
max_concurrency: 1
context_window: 128000
""")

_DEFAULT_COMPRESSOR_CONFIG: dict[str, Any] = {
    "keep_turns": 3,
    "compressed_window": 0.15,
}


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


def build_backend(
    config: dict[str, Any],
) -> tuple[OpenAIBackend | AnthropicBackend, dict[str, Any]]:
    """Build primary backend from config; returns (backend, backends_config)."""
    backends_config = config.get("backends")
    if not isinstance(backends_config, dict):
        raise ValueError("Config must contain a 'backends' section")
    if "primary" not in backends_config:
        raise ValueError("Config 'backends' must contain a 'primary' backend")

    primary_cfg = backends_config["primary"]
    if not isinstance(primary_cfg, dict):
        raise ValueError("Config 'backends.primary' must be a mapping")
    return _build_backend(primary_cfg, "primary"), backends_config


def build_compressor(
    config: dict[str, Any],
    primary_backend: Any,
    backends_config: dict[str, Any],
) -> Any:
    """Build LLMCompressor from config; returns None when disabled."""
    from little_agent.agent.compressor import LLMCompressor

    compressor_section = config.get("compressor")
    if compressor_section is False:
        return None

    if not isinstance(compressor_section, dict):
        compressor_section = _DEFAULT_COMPRESSOR_CONFIG

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
