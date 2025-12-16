"""Provider factory for vision AI services."""

import os
import logging
from typing import Optional
from .base import VisionProvider
from .gemini import GeminiProvider
from .openai import OpenAIProvider


def create_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None
) -> VisionProvider:
    """
    Create a vision provider based on available API keys or explicit selection.

    Auto-detection logic:
    1. If both GEMINI_API_KEY and OPENAI_API_KEY exist → prefer Gemini
    2. If only one exists → use that provider
    3. If neither exists → raise error
    4. Allow explicit provider selection via provider_name parameter

    Args:
        provider_name: Explicit provider choice ('gemini' or 'openai').
                      If None, auto-detect from environment variables
        model_name: Model name to use. If None, use provider defaults:
                   - Gemini: gemini-2.5-flash
                   - OpenAI: gpt-4o

    Returns:
        Configured VisionProvider instance

    Raises:
        ValueError: If no API keys are available or invalid provider specified
    """
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))

    # Auto-detection logic
    if provider_name is None:
        if has_gemini and has_openai:
            logging.info("Both GEMINI_API_KEY and OPENAI_API_KEY found. Defaulting to Gemini.")
            provider_name = "gemini"
        elif has_gemini:
            logging.info("Using Gemini (GEMINI_API_KEY found)")
            provider_name = "gemini"
        elif has_openai:
            logging.info("Using OpenAI (OPENAI_API_KEY found)")
            provider_name = "openai"
        else:
            raise ValueError(
                "No API keys found. Please set GEMINI_API_KEY or OPENAI_API_KEY "
                "environment variable."
            )

    # Create provider
    provider_name = provider_name.lower()

    if provider_name == "gemini":
        if not has_gemini:
            raise ValueError(
                "GEMINI_API_KEY environment variable not set. "
                "Please set it with your Gemini API key."
            )
        model = model_name or "gemini-2.5-flash"
        return GeminiProvider(model_name=model)

    elif provider_name == "openai":
        if not has_openai:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set. "
                "Please set it with your OpenAI API key."
            )
        model = model_name or "gpt-4o"
        return OpenAIProvider(model_name=model)

    else:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Supported providers: gemini, openai"
        )


__all__ = ['VisionProvider', 'GeminiProvider', 'OpenAIProvider', 'create_provider']
