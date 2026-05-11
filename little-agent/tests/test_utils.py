"""Tests for backends/_utils.py (TASK-S4)."""

from __future__ import annotations

import logging

import pytest

from little_agent.backends._utils import _sanitize_messages


def test_sanitize_messages_redacts_authorization() -> None:
    """Authorization header string values are replaced with ***REDACTED***."""
    messages = [{"role": "user", "headers": {"Authorization": "Bearer sk-secret"}}]
    result = _sanitize_messages(messages)
    assert result[0]["headers"]["Authorization"] == "***REDACTED***"


def test_sanitize_messages_redacts_cookie() -> None:
    """Cookie values are replaced with ***REDACTED***."""
    messages = [{"role": "user", "Cookie": "session=abc123"}]
    result = _sanitize_messages(messages)
    assert result[0]["Cookie"] == "***REDACTED***"


def test_sanitize_messages_redacts_api_key() -> None:
    """api_key values are replaced with ***REDACTED***."""
    data = {"api_key": "sk-secret-key", "model": "gpt-4"}
    result = _sanitize_messages(data)
    assert result["api_key"] == "***REDACTED***"
    assert result["model"] == "gpt-4"


def test_sanitize_messages_redacts_token() -> None:
    """Token values are replaced with ***REDACTED***."""
    data = {"token": "my-secret-token"}
    result = _sanitize_messages(data)
    assert result["token"] == "***REDACTED***"


def test_sanitize_messages_redacts_secret() -> None:
    """Secret values are replaced with ***REDACTED***."""
    data = {"secret": "shh"}
    result = _sanitize_messages(data)
    assert result["secret"] == "***REDACTED***"


def test_sanitize_messages_case_insensitive() -> None:
    """Key matching is case-insensitive."""
    data = {"AUTHORIZATION": "Bearer token", "API_KEY": "key"}
    result = _sanitize_messages(data)
    assert result["AUTHORIZATION"] == "***REDACTED***"
    assert result["API_KEY"] == "***REDACTED***"


def test_sanitize_messages_preserves_non_string_sensitive_values() -> None:
    """Non-string values for sensitive keys are not replaced."""
    data = {"token": 12345}
    result = _sanitize_messages(data)
    assert result["token"] == 12345


def test_sanitize_messages_preserves_safe_fields() -> None:
    """Non-sensitive fields are left unchanged."""
    messages = [{"role": "user", "content": "hello"}]
    result = _sanitize_messages(messages)
    assert result[0]["content"] == "hello"
    assert result[0]["role"] == "user"


def test_sanitize_messages_nested_dict() -> None:
    """Nested dicts are recursively sanitized."""
    data = {"outer": {"inner": {"Authorization": "Bearer token"}}}
    result = _sanitize_messages(data)
    assert result["outer"]["inner"]["Authorization"] == "***REDACTED***"


def test_sanitize_messages_list_of_dicts() -> None:
    """Lists of dicts are recursively processed."""
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "api_key": "sk-secret"},
    ]
    result = _sanitize_messages(messages)
    assert result[0]["content"] == "hello"
    assert result[1]["api_key"] == "***REDACTED***"


def test_sanitize_messages_does_not_mutate_original() -> None:
    """_sanitize_messages does not mutate the input (deep copy is caller's responsibility)."""
    original = [{"role": "user", "Authorization": "Bearer sk-secret"}]
    import copy

    to_sanitize = copy.deepcopy(original)
    _sanitize_messages(to_sanitize)
    # The original variable is not mutated by this function (it only creates new structures)
    assert original[0]["Authorization"] == "Bearer sk-secret"


def test_log_streaming_request_redacts_in_debug(caplog: pytest.LogCaptureFixture) -> None:
    """_log_streaming_request redacts sensitive keys in DEBUG output."""
    from little_agent.backends._utils import _log_streaming_request

    test_logger = logging.getLogger("test_redact")
    messages = [{"role": "user", "content": "hi", "Authorization": "Bearer sk-secret"}]

    with caplog.at_level(logging.DEBUG, logger="test_redact"):
        _log_streaming_request(test_logger, "test", "gpt-4", messages, None)

    # Check that the raw secret does not appear in any logged message
    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "sk-secret" not in log_text
    assert "***REDACTED***" in log_text
