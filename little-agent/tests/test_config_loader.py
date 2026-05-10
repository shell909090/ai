"""Tests for tool configuration loader in main."""

from unittest.mock import MagicMock, patch

import pytest

from little_agent.main import load_providers_from_config
from little_agent.tools.bash import BashToolProvider


def test_empty_config_always_includes_bash() -> None:
    """Empty providers config still loads BashToolProvider."""
    result = load_providers_from_config({})
    assert any(isinstance(p, BashToolProvider) for p in result)


def test_extra_provider_loaded() -> None:
    """A class path in providers list is imported and instantiated."""
    fake_instance = MagicMock()
    fake_cls = MagicMock(return_value=fake_instance)
    fake_mod = MagicMock()
    fake_mod.FakeProvider = fake_cls

    config = {"tools": {"providers": ["mypackage.mymod.FakeProvider"]}}

    with patch("importlib.import_module", return_value=fake_mod) as mock_import:
        result = load_providers_from_config(config)

    mock_import.assert_any_call("mypackage.mymod")
    fake_cls.assert_called_once_with()
    assert fake_instance in result


def test_duplicate_provider_loaded_once() -> None:
    """Duplicate class paths result in a single instance."""
    config = {
        "tools": {
            "providers": [
                "little_agent.tools.bash.BashToolProvider",
                "little_agent.tools.bash.BashToolProvider",
            ]
        }
    }
    result = load_providers_from_config(config)
    bash_providers = [p for p in result if isinstance(p, BashToolProvider)]
    assert len(bash_providers) == 1


def test_bad_class_path_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """An invalid class path logs an error and is skipped."""
    config = {"tools": {"providers": ["no_such_module.NoSuchClass"]}}
    result = load_providers_from_config(config)
    bash_providers = [p for p in result if isinstance(p, BashToolProvider)]
    assert len(bash_providers) == 1
    assert any("no_such_module.NoSuchClass" in r.message for r in caplog.records)
