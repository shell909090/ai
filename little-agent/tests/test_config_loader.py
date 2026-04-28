"""Tests for tool configuration loader."""

from unittest.mock import MagicMock, patch

from little_agent.tools.config_loader import load_providers_from_config
from little_agent.tools.protocol import ToolProvider


class FakeProvider(ToolProvider):
    """Fake provider for testing."""

    def list(self):
        return {}

    async def invoke(self, name, **kwargs):
        return "ok"


def test_empty_config_returns_empty() -> None:
    """Test empty config returns empty provider list."""
    result = load_providers_from_config({})
    assert result == []


def test_python_provider_loaded() -> None:
    """Test python provider loaded successfully."""
    fake = FakeProvider()
    mock_module = MagicMock()
    mock_module.create_provider.return_value = fake

    config = {"tools": {"providers": [{"type": "python", "module": "fake_module"}]}}

    with patch("importlib.import_module", return_value=mock_module):
        result = load_providers_from_config(config)
        assert len(result) == 1
        assert result[0] is fake


def test_python_provider_missing_module_skipped() -> None:
    """Test python provider missing module is skipped."""
    config = {"tools": {"providers": [{"type": "python"}]}}

    result = load_providers_from_config(config)
    assert result == []


def test_python_provider_no_create_provider_skipped() -> None:
    """Test python provider without create_provider is skipped."""
    mock_module = MagicMock()
    del mock_module.create_provider

    config = {"tools": {"providers": [{"type": "python", "module": "fake_module"}]}}

    with patch("importlib.import_module", return_value=mock_module):
        result = load_providers_from_config(config)
        assert result == []


def test_python_provider_not_toolprovider_skipped() -> None:
    """Test python provider returning non-ToolProvider is skipped."""
    mock_module = MagicMock()
    mock_module.create_provider.return_value = "not_a_provider"

    config = {"tools": {"providers": [{"type": "python", "module": "fake_module"}]}}

    with patch("importlib.import_module", return_value=mock_module):
        result = load_providers_from_config(config)
        assert result == []


def test_python_provider_import_error_skipped() -> None:
    """Test python provider import failure is skipped."""
    config = {"tools": {"providers": [{"type": "python", "module": "bad_module"}]}}

    with patch("importlib.import_module", side_effect=ImportError("No module")):
        result = load_providers_from_config(config)
        assert result == []


def test_unknown_provider_type_skipped() -> None:
    """Test unknown provider type is skipped with warning."""
    config = {"tools": {"providers": [{"type": "unknown"}]}}

    result = load_providers_from_config(config)
    assert result == []
