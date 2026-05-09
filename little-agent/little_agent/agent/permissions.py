"""Permission system for tool invocation control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from little_agent.types import JSONValue


@dataclass
class PermissionRule:
    """A single permission rule for a tool or default policy."""

    tool: str
    action: Literal["allow", "deny", "ask"]


class PermissionManager:
    """Manages permission rules for tool invocations.

    Rules are evaluated in order; the first matching rule wins.
    If no rule matches, the default policy is applied.
    """

    def __init__(
        self,
        rules: list[PermissionRule] | None = None,
        default: Literal["allow", "deny", "ask"] = "ask",
    ) -> None:
        self._rules = rules or []
        self._default = default

    def check(self, tool_name: str) -> Literal["allow", "deny", "ask"]:
        """Return the action for a given tool name."""
        for rule in self._rules:
            if rule.tool == tool_name:
                return rule.action
        return self._default

    @classmethod
    def from_config(cls, config: dict[str, JSONValue] | None) -> "PermissionManager":
        """Build a PermissionManager from a config dict.

        Expected config shape::

            permissions:
              default: allow   # or deny, ask
              rules:
                - tool: bash
                  action: ask
                - tool: rm
                  action: deny
        """
        if config is None:
            return cls()

        default_raw = str(config.get("default", "ask"))
        if default_raw not in ("allow", "deny", "ask"):
            default_raw = "ask"
        default: Literal["allow", "deny", "ask"] = default_raw  # type: ignore[assignment]

        rules: list[PermissionRule] = []
        rules_raw = config.get("rules", [])
        if isinstance(rules_raw, list):
            for r in rules_raw:
                if isinstance(r, dict):
                    tool = r.get("tool", "")
                    action_raw = r.get("action", "allow")
                    if isinstance(tool, str) and isinstance(action_raw, str):
                        action: Literal["allow", "deny", "ask"] = action_raw  # type: ignore[assignment]
                        if action in ("allow", "deny", "ask"):
                            rules.append(PermissionRule(tool=tool, action=action))

        return cls(rules=rules, default=default)
