"""Tests for dict-based tool provider loading."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from little_agent.main import load_providers_from_config
from little_agent.tools.bash import BashToolProvider


def test_empty_providers_dict_returns_no_providers() -> None:
    """Empty providers dict yields no providers and task_enabled=False."""
    providers, task_enabled = load_providers_from_config({"tools": {"providers": {}}})
    assert providers == []
    assert task_enabled is False


def test_bash_provider_loaded_with_args() -> None:
    """BashToolProvider is instantiated with constructor args from config."""
    config = {
        "tools": {
            "providers": {
                "little_agent.tools.bash.BashToolProvider": {"timeout": 60, "max_timeout": 3600}
            }
        }
    }
    providers, task_enabled = load_providers_from_config(config)
    assert len(providers) == 1
    assert isinstance(providers[0], BashToolProvider)
    assert providers[0]._timeout == 60
    assert providers[0]._max_timeout == 3600
    assert task_enabled is False


def test_task_provider_detected_not_instantiated() -> None:
    """TaskToolProvider in config sets task_enabled=True but is not in providers list."""
    config = {
        "tools": {
            "providers": {
                "little_agent.tools.task.TaskToolProvider": {},
            }
        }
    }
    providers, task_enabled = load_providers_from_config(config)
    assert providers == []
    assert task_enabled is True


def test_custom_provider_loaded_with_args() -> None:
    """A custom class path is imported and instantiated with given args."""
    fake_instance = MagicMock()
    fake_cls = MagicMock(return_value=fake_instance)
    fake_mod = MagicMock()
    fake_mod.FakeProvider = fake_cls

    config = {"tools": {"providers": {"mypackage.mymod.FakeProvider": {"key": "value"}}}}

    with patch("importlib.import_module", return_value=fake_mod) as mock_import:
        providers, _ = load_providers_from_config(config)

    mock_import.assert_any_call("mypackage.mymod")
    fake_cls.assert_called_once_with(key="value")
    assert fake_instance in providers


def test_args_none_raises_value_error() -> None:
    """Provider with null args raises ValueError with Use {} hint."""
    config = {"tools": {"providers": {"little_agent.tools.bash.BashToolProvider": None}}}
    with pytest.raises(ValueError, match="Use {} for no-arg providers"):
        load_providers_from_config(config)


def test_args_non_dict_raises_value_error() -> None:
    """Provider with non-dict args raises ValueError."""
    config = {"tools": {"providers": {"little_agent.tools.bash.BashToolProvider": "invalid"}}}
    with pytest.raises(ValueError, match="must be a dict"):
        load_providers_from_config(config)


def test_invalid_class_path_raises_import_error() -> None:
    """A class path that cannot be imported raises ImportError with full path."""
    config = {"tools": {"providers": {"no_such_module.NoSuchClass": {}}}}
    with pytest.raises(ImportError, match="no_such_module.NoSuchClass"):
        load_providers_from_config(config)


def test_missing_class_in_module_raises_import_error() -> None:
    """A valid module but missing class raises ImportError."""
    fake_mod = MagicMock(spec=[])  # no attributes
    fake_mod.NoSuchClass = None

    config = {"tools": {"providers": {"mypackage.mymod.NoSuchClass": {}}}}
    with patch("importlib.import_module", return_value=fake_mod):
        # getattr returns None → class not found
        with pytest.raises(ImportError, match="Provider class not found"):
            load_providers_from_config(config)


def test_old_list_format_raises_value_error() -> None:
    """Old list-format tools.providers raises ValueError."""
    config = {"tools": {"providers": ["little_agent.tools.bash.BashToolProvider"]}}
    with pytest.raises(ValueError, match="Old list format is not supported"):
        load_providers_from_config(config)


def test_old_task_tool_field_raises_value_error() -> None:
    """Old tools.task_tool field raises ValueError with migration hint."""
    config = {"tools": {"task_tool": True, "providers": {}}}
    with pytest.raises(ValueError, match="task_tool.*no longer supported"):
        load_providers_from_config(config)


def test_old_bash_field_raises_value_error() -> None:
    """Old tools.bash.* field raises ValueError with migration hint."""
    config = {"tools": {"bash": {"timeout": 30}, "providers": {}}}
    with pytest.raises(ValueError, match="tools.bash.*no longer supported"):
        load_providers_from_config(config)


def test_no_tools_section_returns_empty() -> None:
    """Missing tools section yields empty providers and task_enabled=False."""
    providers, task_enabled = load_providers_from_config({})
    assert providers == []
    assert task_enabled is False
