"""Tests for dict-based tool provider loading."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.agent.tool_setup import (
    _import_provider,
    build_tools,
    load_providers_from_config,
    parse_mcp_configs,
    start_mcp_providers,
)
from little_agent.main import _DEFAULT_CONFIG, _deep_merge
from little_agent.tools.bash import BashProvider


def test_empty_providers_dict_returns_no_providers() -> None:
    """Empty providers dict yields no providers and task_enabled=False."""
    providers, task_enabled = load_providers_from_config({"tools": {"providers": {}}})
    assert providers == []
    assert task_enabled is False


def test_bash_provider_loaded_with_args() -> None:
    """BashProvider is instantiated with constructor args from config."""
    config = {
        "tools": {
            "providers": {
                "little_agent.tools.bash.BashProvider": {"timeout": 60, "max_timeout": 3600}
            }
        }
    }
    providers, task_enabled = load_providers_from_config(config)
    assert len(providers) == 1
    assert isinstance(providers[0], BashProvider)
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


def test_args_none_skips_provider() -> None:
    """Provider with null args is silently skipped (opt-out from default)."""
    config = {"tools": {"providers": {"little_agent.tools.bash.BashProvider": None}}}
    providers, task_enabled = load_providers_from_config(config)
    assert providers == []
    assert task_enabled is False


def test_args_non_dict_raises_value_error() -> None:
    """Provider with non-dict args raises ValueError."""
    config = {"tools": {"providers": {"little_agent.tools.bash.BashProvider": "invalid"}}}
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
    config = {"tools": {"providers": ["little_agent.tools.bash.BashProvider"]}}
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


def test_default_config_injects_bash() -> None:
    """After _deep_merge with _DEFAULT_CONFIG, bash provider is auto-loaded."""
    # Merging an empty user config with defaults yields the default providers.
    merged = _deep_merge(_DEFAULT_CONFIG, {})
    providers, task_enabled = load_providers_from_config(merged)
    assert any(isinstance(p, BashProvider) for p in providers)
    assert task_enabled is True


# ── _import_provider ─────────────────────────────────────────────────────────


def test_import_provider_no_dot_in_path_raises() -> None:
    """A class path without a dot (no module component) raises ImportError."""
    with pytest.raises(ImportError, match="Invalid provider class path"):
        _import_provider("NoDotClass", {})


def test_import_provider_class_not_found_raises() -> None:
    """A valid module but missing class attribute raises ImportError."""
    fake_mod = MagicMock(spec=[])  # no attributes at all
    # Make getattr return None for the missing class
    with patch("importlib.import_module", return_value=fake_mod):
        with pytest.raises(ImportError, match="Provider class not found"):
            _import_provider("mypackage.mymod.ReallyMissingClass", {})


# ── load_providers_from_config: non-dict tools config ───────────────────────


def test_non_dict_tools_config_treated_as_empty() -> None:
    """Non-dict tools value is silently coerced to empty; returns no providers."""
    providers, task_enabled = load_providers_from_config({"tools": "not_a_dict"})
    assert providers == []
    assert task_enabled is False


def test_none_tools_section_treated_as_empty() -> None:
    """Explicit tools: null is treated as empty config."""
    providers, task_enabled = load_providers_from_config({"tools": None})
    assert providers == []
    assert task_enabled is False


# ── build_tools: registration failure ────────────────────────────────────────


def test_build_tools_register_failure_warns_and_skips() -> None:
    """If a provider registration raises ValueError, it is logged and skipped."""
    from little_agent.agent.tool_manager import ToolManager

    # Pre-fill a ToolManager with BashProvider so a second registration conflicts.
    pre_filled = ToolManager()
    pre_filled.register(BashProvider())

    config = {"tools": {"providers": {"little_agent.tools.bash.BashProvider": {}}}}

    with patch("little_agent.agent.tool_setup.logger") as mock_logger:
        with patch("little_agent.agent.tool_setup.ToolManager", return_value=pre_filled):
            result_tools, task_enabled = build_tools(config)

    mock_logger.warning.assert_called_once()
    assert task_enabled is False


# ── parse_mcp_configs ────────────────────────────────────────────────────────


def test_parse_mcp_configs_no_tools_key() -> None:
    """No tools: key returns empty list."""
    assert parse_mcp_configs({}) == []


def test_parse_mcp_configs_no_mcp_key() -> None:
    """tools.mcp absent returns empty list."""
    assert parse_mcp_configs({"tools": {}}) == []


def test_parse_mcp_configs_non_dict_mcp_raises() -> None:
    """tools.mcp is not a dict raises ValueError."""
    with pytest.raises(ValueError, match="must be a dict"):
        parse_mcp_configs({"tools": {"mcp": ["invalid"]}})


def test_parse_mcp_configs_server_non_dict_raises() -> None:
    """MCP server config that is not a dict raises ValueError."""
    with pytest.raises(ValueError, match="config must be a dict"):
        parse_mcp_configs({"tools": {"mcp": {"weather": "not-a-dict"}}})


def test_parse_mcp_configs_missing_command_raises() -> None:
    """MCP server config without command raises ValueError."""
    with pytest.raises(ValueError, match="'command' is required"):
        parse_mcp_configs({"tools": {"mcp": {"weather": {"env": {}}}}})


def test_parse_mcp_configs_non_list_command_raises() -> None:
    """MCP server config with non-list command raises ValueError."""
    with pytest.raises(ValueError, match="must be a list of strings"):
        parse_mcp_configs({"tools": {"mcp": {"weather": {"command": "python server.py"}}}})


def test_parse_mcp_configs_non_string_command_items_raises() -> None:
    """MCP server config with non-string command items raises ValueError."""
    with pytest.raises(ValueError, match="must be a list of strings"):
        parse_mcp_configs({"tools": {"mcp": {"weather": {"command": ["python", 42]}}}})


def test_parse_mcp_configs_valid_returns_pairs() -> None:
    """Valid MCP config returns correct (name, cfg) tuples."""
    config = {
        "tools": {
            "mcp": {
                "weather": {"command": ["python", "server.py"]},
                "fs": {"command": ["node", "fs.js"], "env": {"K": "V"}},
            }
        }
    }
    result = parse_mcp_configs(config)
    assert len(result) == 2
    names = [name for name, _ in result]
    assert "weather" in names
    assert "fs" in names


# ── start_mcp_providers ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_mcp_providers_start_failure_logs_and_skips() -> None:
    """A provider that fails to start is logged; other providers are unaffected."""
    from little_agent.agent.tool_manager import ToolManager

    failing_provider = MagicMock()
    failing_provider.start = AsyncMock(side_effect=Exception("connect failed"))

    tools = ToolManager()

    # MCPStdioProvider is imported inside start_mcp_providers, so patch its source module.
    with patch("little_agent.tools.mcp.MCPStdioProvider", return_value=failing_provider):
        with patch("little_agent.agent.tool_setup.logger") as mock_logger:
            providers = await start_mcp_providers(
                [("failing", {"command": ["python", "server.py"]})], tools
            )

    assert providers == []
    mock_logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_start_mcp_providers_success_registers_provider() -> None:
    """A provider that starts successfully is registered in tools and returned."""
    from little_agent.agent.tool_manager import ToolManager

    working_provider = MagicMock()
    working_provider.start = AsyncMock(return_value=None)
    working_provider.__iter__ = MagicMock(return_value=iter([]))  # empty ToolProvider

    tools = ToolManager()

    with patch("little_agent.tools.mcp.MCPStdioProvider", return_value=working_provider):
        providers = await start_mcp_providers([("ok", {"command": ["python", "server.py"]})], tools)

    assert working_provider in providers
