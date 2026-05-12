"""Factory functions for assembling frontend client, hooks, and permissions from config."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_agent.frontends.acp import AcpClient
from little_agent.frontends.cli import CliClient
from little_agent.frontends.web import WebClient

if TYPE_CHECKING:
    from little_agent.agent.protocol import Agent, PermissionChecker

logger = logging.getLogger(__name__)


def build_client(
    config: dict[str, Any],
    session_store: Any,
) -> tuple[Any, str]:
    """Build the frontend client; returns (client, frontend_type)."""
    frontend_cfg = config.get("frontend") or {}
    frontend_type = str(frontend_cfg.get("type", "cli"))

    if frontend_type == "web":
        sessions_dir_raw = (
            frontend_cfg.get("sessions_dir") if isinstance(frontend_cfg, dict) else None
        )
        if sessions_dir_raw:
            sessions_dir: Path | None = Path(str(sessions_dir_raw)).expanduser()
        else:
            sessions_dir = Path("~/.local/state/little_agent/sessions").expanduser()
        client: CliClient | WebClient | AcpClient = WebClient(
            sessions_dir=sessions_dir, jsonl_store=session_store
        )
    elif frontend_type == "acp":
        client = AcpClient()
    else:
        client = CliClient()

    return client, frontend_type


def build_hooks(config: dict[str, Any]) -> list[Any]:
    """Build hooks list from config; raises if deprecated loggers: key found."""
    if "loggers" in config:
        raise ValueError("Rename `loggers:` to `hooks:` or migrate to `session_store:`")
    hooks_cfg = config.get("hooks")
    if hooks_cfg is None:
        return []
    if not isinstance(hooks_cfg, list):
        logger.warning("hooks config is not a list; ignored")
        return []
    for item in hooks_cfg:
        if isinstance(item, dict):
            hook_type = item.get("type")
            raise ValueError(
                f"Unknown hook type: {hook_type!r}. "
                "No built-in hook types are registered via hooks:. "
                "Use session_store: for SessionJSONLStore."
            )
    return []


def build_permissions(config: dict[str, Any], client: PermissionChecker) -> PermissionChecker:
    """Build permission chain from config list, with client as terminal."""
    permissions_cfg = config.get("permissions")
    if isinstance(permissions_cfg, dict):
        logger.warning(
            "permissions config is a dict (old format); ignored. "
            "Use a list of checkers: [{type: blackwhitelist, ...}]"
        )
        return client
    if isinstance(permissions_cfg, list):
        from little_agent.agent.permissions import build_permission_chain

        return build_permission_chain(permissions_cfg, client)
    return client


async def run_frontend(
    client: Any,
    agent: Agent,
    config: dict[str, Any],
    frontend_type: str,
    initial_prompt: str | None,
) -> None:
    """Start and run the selected frontend."""
    if frontend_type == "web":
        cfg = config.get("frontend", {})
        host = cfg.get("host", "127.0.0.1") if isinstance(cfg, dict) else "127.0.0.1"
        port_raw = cfg.get("port", 8080) if isinstance(cfg, dict) else 8080
        port = int(port_raw) if isinstance(port_raw, (int, float)) else 8080
        await client.run(agent, host=str(host), port=port)
    elif frontend_type == "cli":
        await client.run(agent, initial_prompt=initial_prompt)
    else:
        await client.run(agent)
