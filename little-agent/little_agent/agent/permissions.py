"""Permission system for tool invocation control."""

from __future__ import annotations

import fnmatch
import logging
from typing import TYPE_CHECKING

from little_agent.types import JSONValue, PermissionChecker

if TYPE_CHECKING:
    from little_agent.types import Session

logger = logging.getLogger(__name__)


class YesManChecker:
    """Always grants permission."""

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        return True


class BlackWhiteListChecker:
    """Permission checker with fnmatch pattern lists. Blacklist takes priority over whitelist."""

    def __init__(
        self,
        blacklist: list[str],
        whitelist: list[str],
        next_checker: PermissionChecker,
    ) -> None:
        self._blacklist = blacklist
        self._whitelist = whitelist
        self._next = next_checker

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool:
        for pattern in self._blacklist:
            if fnmatch.fnmatch(kind, pattern):
                return False
        for pattern in self._whitelist:
            if fnmatch.fnmatch(kind, pattern):
                return True
        return await self._next.request_permission(session, kind, payload)


def build_permission_chain(
    config_list: list[dict[str, JSONValue]],
    terminal: PermissionChecker,
) -> PermissionChecker:
    """Build a permission chain from config list with terminal as fallback."""
    checker: PermissionChecker = terminal
    for cfg in reversed(config_list):
        checker_type = cfg.get("type")
        if checker_type == "yesman":
            checker = YesManChecker()
        elif checker_type == "blackwhitelist":
            blacklist_raw = cfg.get("blacklist", [])
            whitelist_raw = cfg.get("whitelist", [])
            blacklist = [str(p) for p in blacklist_raw] if isinstance(blacklist_raw, list) else []
            whitelist = [str(p) for p in whitelist_raw] if isinstance(whitelist_raw, list) else []
            checker = BlackWhiteListChecker(
                blacklist=blacklist, whitelist=whitelist, next_checker=checker
            )
        else:
            raise ValueError(f"Unknown permission checker type: {checker_type!r}")
    return checker
