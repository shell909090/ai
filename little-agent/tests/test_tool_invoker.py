"""Unit tests for ToolInvoker._check."""

from __future__ import annotations

from unittest.mock import MagicMock

from little_agent.agent.tool_invoker import ToolInvoker
from little_agent.backends.protocol import BackendToolCall


def _make_invoker(permissions=None, turn_allowed_tools=None):
    session = MagicMock()
    session.agent.permissions = permissions
    session._turn_allowed_tools = turn_allowed_tools
    return ToolInvoker(session)


def _tc(tool_name: str) -> BackendToolCall:
    return BackendToolCall(call_id="c1", tool_name=tool_name, arguments={})


class TestCheckNoAllowedNames:
    """Tests where allowed_names=None (no turn-level restriction)."""

    def test_no_allowed_names_no_permissions_returns_allow(self):
        """When allowed_names is None and agent has no permissions, allow unconditionally."""
        invoker = _make_invoker(permissions=None)
        result = invoker._check(_tc("echo"), allowed_names=None)
        assert result == ("allow", None)

    def test_no_allowed_names_permissions_allow(self):
        """When permissions.check returns 'allow', _check propagates it with no error."""
        permissions = MagicMock()
        permissions.check.return_value = "allow"
        invoker = _make_invoker(permissions=permissions)
        result = invoker._check(_tc("echo"), allowed_names=None)
        assert result == ("allow", None)
        permissions.check.assert_called_once_with("echo")

    def test_no_allowed_names_permissions_ask(self):
        """When permissions.check returns 'ask', _check propagates it with no error."""
        permissions = MagicMock()
        permissions.check.return_value = "ask"
        invoker = _make_invoker(permissions=permissions)
        result = invoker._check(_tc("bash"), allowed_names=None)
        assert result == ("ask", None)
        permissions.check.assert_called_once_with("bash")

    def test_no_allowed_names_permissions_deny(self):
        """When permissions.check returns 'deny', _check propagates it with no error."""
        permissions = MagicMock()
        permissions.check.return_value = "deny"
        invoker = _make_invoker(permissions=permissions)
        result = invoker._check(_tc("rm"), allowed_names=None)
        assert result == ("deny", None)
        permissions.check.assert_called_once_with("rm")


class TestCheckWithAllowedNames:
    """Tests where allowed_names restricts the tool set."""

    def test_tool_in_allowed_names_no_permissions_returns_allow(self):
        """Tool present in allowed_names and no permissions → allow."""
        invoker = _make_invoker(permissions=None)
        result = invoker._check(_tc("echo"), allowed_names={"echo"})
        assert result == ("allow", None)

    def test_tool_not_in_allowed_names_returns_deny_with_message(self):
        """Tool absent from allowed_names returns deny with descriptive error."""
        invoker = _make_invoker(permissions=None)
        result = invoker._check(_tc("bash"), allowed_names={"echo"})
        assert result == ("deny", "Tool not in allowed list: bash")

    def test_allowed_names_checked_before_permissions(self):
        """allowed_names gate fires before permissions.check; deny wins."""
        permissions = MagicMock()
        permissions.check.return_value = "allow"
        invoker = _make_invoker(permissions=permissions)
        result = invoker._check(_tc("bash"), allowed_names={"echo"})
        assert result == ("deny", "Tool not in allowed list: bash")
        permissions.check.assert_not_called()
