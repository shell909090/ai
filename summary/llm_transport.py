"""Small HTTP transport for OpenAI-compatible chat endpoints."""

import os
from types import SimpleNamespace

import httpx


class RateLimitError(RuntimeError):
    """The server rejected a request due to rate limiting."""

    def __init__(self, message: str, **kwargs: object) -> None:
        super().__init__(message)


def _config(model: str) -> tuple[str, str, str]:
    if not model:
        raise ValueError("Set MODEL or pass --model")
    provider, separator, name = model.partition("/")
    if not separator or not name:
        raise ValueError("Model must use provider/model format")
    endpoints = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "cohere": "https://api.cohere.com/v2",
        "groq": "https://api.groq.com/openai/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    if provider not in endpoints:
        raise ValueError(f"Unsupported provider: {provider}; use an openai/ compatible gateway")
    key = os.getenv(f"{provider.upper()}_API_KEY", "")
    if provider == "gemini":
        key = key or os.getenv("GOOGLE_API_KEY", "")
    base = os.getenv(f"{provider.upper()}_API_BASE") or endpoints[provider]
    return base.rstrip("/"), key, name


def validate_environment(model: str) -> dict:
    """Validate model routing and required API credentials."""
    _, key, _ = _config(model)
    return {"keys_in_environment": bool(key), "missing_keys": [f"{model.split('/')[0].upper()}_API_KEY"]}


def ModelResponse(choices: list[dict]) -> SimpleNamespace:
    """Decode the text response envelope."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(**c["message"])) for c in choices])


def completion(model: str, messages: list[dict[str, str]], temperature: float,
               extra_headers: dict[str, str]) -> SimpleNamespace:
    """Send a chat request with an explicit timeout."""
    base, key, name = _config(model)
    provider = model.split("/", 1)[0]
    headers = {**extra_headers, "Authorization": f"Bearer {key}"}
    payload = {"model": name, "messages": messages, "temperature": temperature}
    path = "chat/completions"
    if provider == "anthropic":
        path = "messages"
        headers = {**extra_headers, "x-api-key": key, "anthropic-version": "2023-06-01"}
        payload = {**payload, "max_tokens": 4096,
                   "system": messages[0]["content"], "messages": messages[1:]}
    elif provider == "cohere":
        path = "chat"
    response = httpx.post(f"{base}/{path}", timeout=60, headers=headers, json=payload)
    if response.status_code == 429:
        raise RateLimitError("LLM rate limit exceeded")
    response.raise_for_status()
    data = response.json()
    if provider in {"anthropic", "cohere"}:
        blocks = data["content"] if provider == "anthropic" else data["message"]["content"]
        content = "".join(block["text"] for block in blocks if block["type"] == "text")
        return ModelResponse([{"message": {"content": content}}])
    return ModelResponse(data["choices"])
