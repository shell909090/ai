"""Main entry point for little-agent CLI."""

from __future__ import annotations

import argparse
import asyncio
import logging
import logging.config
from pathlib import Path
from typing import Any

import yaml

from little_agent._utils import _deep_merge
from little_agent.agent.agent import AgentCore
from little_agent.agent.tool_manager import ToolManager
from little_agent.agent.tool_setup import build_tools, parse_mcp_configs, start_mcp_providers
from little_agent.backends.build import build_backend, build_compressor
from little_agent.frontends.build import build_client, build_hooks, build_permissions, run_frontend
from little_agent.tools.task import TaskToolProvider

logger = logging.getLogger(__name__)


class _ContextFilter(logging.Filter):
    """Inject session_id and turn_id from ContextVars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        from little_agent.agent.context import current_session_id, current_turn_id

        record.session_id = current_session_id.get("-")
        record.turn_id = current_turn_id.get("-")
        return True


def setup_logging(config: dict[str, Any], level: str | None) -> None:
    """Configure logging from the merged config dict."""
    if level is not None:
        config.setdefault("loggers", {}).setdefault("", {})["level"] = level
    logging.config.dictConfig(config)
    logging.getLogger().addFilter(_ContextFilter())


def load_config(path: Path) -> dict[str, Any]:
    """Load YAML configuration."""
    with open(path.expanduser(), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping")
    return data


_DEFAULT_CONFIG: dict[str, Any] = yaml.safe_load("""
tools:
  providers:
    little_agent.tools.bash.BashToolProvider:
      timeout: 30
      max_timeout: 1800
    little_agent.tools.task.TaskToolProvider: {}
agent:
  compress_threshold: 0.75
  max_tool_result_chars: 50000
  ignore_agentsmd: false
compressor:
  keep_turns: 3
  compressed_window: 0.15
frontend:
  type: cli
logging:
  version: 1
  disable_existing_loggers: false
  formatters:
    default:
      format: "%(asctime)s [%(levelname)s] %(session_id).8s %(turn_id).8s %(name)s: %(message)s"
  handlers:
    console:
      class: logging.StreamHandler
      formatter: default
      stream: "ext://sys.stdout"
  loggers:
    "":
      level: INFO
      handlers: [console]
""")


def _load_session_store(
    config: dict[str, Any],
    frontend_type: str,
    frontend_cfg: dict[str, Any],
) -> Any:
    """Load SessionJSONLStore from session_store: config, or auto-inject for web frontend."""
    from little_agent.agent.session_store import SessionJSONLStore

    session_store_cfg = config.get("session_store")
    if isinstance(session_store_cfg, dict):
        sessions_dir = str(
            session_store_cfg.get("sessions_dir", "~/.local/state/little_agent/sessions/")
        )
        filename_template = str(
            session_store_cfg.get("filename_template", "{session_id}_session.jsonl")
        )
        return SessionJSONLStore(sessions_dir=sessions_dir, filename_template=filename_template)
    elif session_store_cfg is None and frontend_type == "web":
        # Auto-inject for web frontend using the same sessions_dir as the web client.
        sessions_dir_raw = frontend_cfg.get("sessions_dir", "~/.local/state/little_agent/sessions/")
        store = SessionJSONLStore(sessions_dir=str(sessions_dir_raw))
        logger.info("session_store auto-enabled for web frontend")
        return store
    return None


async def _async_main(
    client: Any,
    agent: AgentCore,
    tools: ToolManager,
    config: dict[str, Any],
    frontend_type: str,
    initial_prompt: str | None,
    mcp_cfgs: list[tuple[str, dict[str, Any]]],
) -> None:
    """Async entry: start MCP providers, run frontend, stop providers on exit."""
    mcp_providers = await start_mcp_providers(mcp_cfgs, tools)
    try:
        await run_frontend(client, agent, config, frontend_type, initial_prompt)
    finally:
        for provider in mcp_providers:
            try:
                await provider.stop()
            except Exception:
                logger.exception("Failed to stop MCP provider")


def _redirect_acp_logging(config: dict[str, Any]) -> None:
    """For ACP mode: redirect stdout log handlers to stderr (ACP uses stdout for JSON-RPC)."""
    for _h in config.get("logging", {}).get("handlers", {}).values():
        if isinstance(_h, dict) and _h.get("stream") in (None, "ext://sys.stdout"):
            _h["stream"] = "ext://sys.stderr"


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Little Agent CLI")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--loglevel", default=None, help="Override log level (DEBUG/INFO/WARNING/ERROR)"
    )
    parser.add_argument(
        "--mode",
        default=None,
        choices=["cli", "web", "acp"],
        help="Override frontend.type from config (cli/web/acp)",
    )
    parser.add_argument(
        "--prompt", default=None, help="Send an initial prompt automatically on startup (CLI only)"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    config = _deep_merge(_DEFAULT_CONFIG, config)

    if args.mode is not None:
        config.setdefault("frontend", {})["type"] = args.mode

    if str((config.get("frontend") or {}).get("type", "cli")) == "acp":
        _redirect_acp_logging(config)

    setup_logging(config["logging"], args.loglevel)

    if "memory" in config:
        raise ValueError(
            "'memory:' config key is no longer supported. "
            "Use session_store: for session history search."
        )

    tools, task_enabled = build_tools(config)
    backend, backends_config = build_backend(config)
    compressor, compressed_window_tokens = build_compressor(config, backend, backends_config)

    frontend_cfg = config.get("frontend") or {}
    frontend_type = str(frontend_cfg.get("type", "cli"))
    session_store = _load_session_store(config, frontend_type, frontend_cfg)
    hooks = build_hooks(config)
    if session_store is not None:
        hooks.append(session_store)

    client, frontend_type = build_client(config, session_store)
    permissions = build_permissions(config, client)

    compress_threshold = float(config["agent"]["compress_threshold"])
    if not (0 < compress_threshold <= 1):
        raise ValueError(
            f"agent.compress_threshold must be in range (0, 1], got {compress_threshold}"
        )

    max_tool_result_chars = int(config["agent"]["max_tool_result_chars"])
    if max_tool_result_chars <= 0:
        raise ValueError(f"agent.max_tool_result_chars must be > 0, got {max_tool_result_chars}")

    primary_system_prompt = (config.get("backends") or {}).get("primary", {}).get("system") or None
    ignore_agentsmd = bool(config["agent"].get("ignore_agentsmd", False))
    agent = AgentCore(
        client=client,
        backend=backend,
        tools=tools,
        compressor=compressor,
        permissions=permissions,
        hooks=hooks,
        compress_threshold=compress_threshold,
        context_window=backend.context_window,
        max_tool_result_chars=max_tool_result_chars,
        system_prompt=primary_system_prompt,
        compressed_window_tokens=compressed_window_tokens,
        ignore_agentsmd=ignore_agentsmd,
    )

    if session_store is not None:
        tools.register(session_store)

    if task_enabled:
        tools.register(TaskToolProvider(agent))

    mcp_cfgs = parse_mcp_configs(config)

    asyncio.run(_async_main(client, agent, tools, config, frontend_type, args.prompt, mcp_cfgs))


if __name__ == "__main__":
    main()
