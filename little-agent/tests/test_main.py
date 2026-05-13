"""Tests for main entry point."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.agent.permissions import YesManChecker
from little_agent.backends.build import _build_backend
from little_agent.frontends.build import (
    build_client,
    build_hooks,
    run_frontend,
)
from little_agent.frontends.build import (
    build_permissions as _load_permissions,
)
from little_agent.main import (
    _DEFAULT_CONFIG,
    _ContextFilter,
    _deep_merge,
    _load_session_store,
    _redirect_acp_logging,
    load_config,
    main,
    setup_logging,
)

_DEFAULT_LOGGING = _DEFAULT_CONFIG["logging"]


def test_setup_logging_default_config() -> None:
    """Test setup_logging with default logging config produces INFO level."""
    with patch("logging.config.dictConfig") as mock_dict_config:
        setup_logging(dict(_DEFAULT_LOGGING), None)
        assert mock_dict_config.called
        cfg = mock_dict_config.call_args.args[0]
        assert cfg["loggers"][""]["level"] == "INFO"


def test_setup_logging_override_level() -> None:
    """Test setup_logging overrides level via --loglevel."""
    with patch("logging.config.dictConfig") as mock_dict_config:
        setup_logging(dict(_DEFAULT_LOGGING), "DEBUG")
        assert mock_dict_config.called
        cfg = mock_dict_config.call_args.args[0]
        assert cfg["loggers"][""]["level"] == "DEBUG"


def test_setup_logging_config_provided() -> None:
    """Test setup_logging uses provided config."""
    with patch("logging.config.dictConfig") as mock_dict_config:
        setup_logging({"version": 1, "loggers": {"": {"level": "WARNING"}}}, None)
        assert mock_dict_config.called
        cfg = mock_dict_config.call_args.args[0]
        assert cfg["loggers"][""]["level"] == "WARNING"


def test_setup_logging_config_with_level_override() -> None:
    """Test --loglevel overrides config level."""
    with patch("logging.config.dictConfig") as mock_dict_config:
        setup_logging({"version": 1, "loggers": {"": {"level": "WARNING"}}}, "DEBUG")
        assert mock_dict_config.called
        cfg = mock_dict_config.call_args.args[0]
        assert cfg["loggers"][""]["level"] == "DEBUG"


def test_load_config() -> None:
    """Test load_config reads YAML file."""
    with patch("builtins.open", MagicMock()):
        with patch("yaml.safe_load", return_value={"backends": {"primary": {"type": "openai"}}}):
            result = load_config(Path("config.yaml"))
            assert result == {"backends": {"primary": {"type": "openai"}}}


def _mock_config(primary_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    primary = {
        "type": "openai",
        "model": "gpt-4",
        "api_key_env": "OPENAI_API_KEY",
        **(primary_overrides or {}),
    }
    return {
        "backends": {"primary": primary},
        "logging": {"version": 1, "loggers": {"": {"level": "INFO"}}},
        "tools": {"providers": {}},
    }


def test_main_success() -> None:
    """Test main successful execution with backends config."""
    mock_config = _mock_config()

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("os.environ.get", return_value="test-key"):
                with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                    with patch("little_agent.frontends.build.CliClient") as mock_client_cls:
                        mock_client = MagicMock()
                        mock_client.run = AsyncMock(return_value=None)
                        mock_client_cls.return_value = mock_client
                        mock_backend_cls.return_value = MagicMock()

                        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                            mock_parse.return_value = MagicMock(
                                config=Path("config.yaml"), loglevel=None, mode=None
                            )
                            main()

                        mock_client.run.assert_called_once()


def test_main_unsupported_backend_raises() -> None:
    """Test main raises ValueError for unsupported backend type."""
    mock_config = _mock_config({"type": "unsupported"})

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                mock_parse.return_value = MagicMock(
                    config=Path("config.yaml"), loglevel=None, mode=None
                )  # noqa: E501
                with pytest.raises(ValueError, match="Unsupported backend type"):
                    main()


def test_main_missing_backends_raises() -> None:
    """Test main raises ValueError when backends section is missing."""
    mock_config = {
        "logging": {"version": 1, "loggers": {"": {"level": "INFO"}}},
        "tools": {"providers": {}},
    }

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                mock_parse.return_value = MagicMock(
                    config=Path("config.yaml"), loglevel=None, mode=None
                )  # noqa: E501
                with pytest.raises(ValueError, match="Config must contain a 'backends' section"):
                    main()


def test_main_missing_primary_raises() -> None:
    """Test main raises ValueError when primary backend is missing."""
    mock_config = {
        "backends": {"compressor": {"type": "openai", "api_key": "k"}},
        "logging": {"version": 1, "loggers": {"": {"level": "INFO"}}},
        "tools": {"providers": {}},
    }

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                mock_parse.return_value = MagicMock(
                    config=Path("config.yaml"), loglevel=None, mode=None
                )  # noqa: E501
                with pytest.raises(ValueError, match="'primary'"):
                    main()


def test_main_missing_api_key_raises() -> None:
    """Test main raises ValueError when no API key configured."""
    mock_config = _mock_config({"api_key_env": "MISSING_KEY"})

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("os.environ.get", return_value=None):
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(
                        config=Path("config.yaml"), loglevel=None, mode=None
                    )  # noqa: E501
                    with pytest.raises(ValueError, match="No API key for backend 'primary'"):
                        main()


def test_main_api_key_from_config() -> None:
    """Test main uses api_key directly from config."""
    mock_config = _mock_config({"api_key": "direct-key"})
    del mock_config["backends"]["primary"]["api_key_env"]

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                with patch("little_agent.frontends.build.CliClient") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client.run = AsyncMock(return_value=None)
                    mock_client_cls.return_value = mock_client
                    mock_backend_cls.return_value = MagicMock()

                    with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                        mock_parse.return_value = MagicMock(
                            config=Path("config.yaml"), loglevel=None
                        )
                        main()

                    mock_backend_cls.assert_called_once_with(
                        model="gpt-4",
                        api_key="direct-key",
                        base_url=None,
                        timeout=60.0,
                        max_concurrency=1,
                        context_window=128000,
                    )


def test_main_api_key_priority_over_env() -> None:
    """Test config api_key takes priority over api_key_env."""
    mock_config = _mock_config({"api_key": "direct-key", "api_key_env": "OPENAI_API_KEY"})

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("os.environ.get", return_value="env-key"):
                with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                    with patch("little_agent.frontends.build.CliClient") as mock_client_cls:
                        mock_client = MagicMock()
                        mock_client.run = AsyncMock(return_value=None)
                        mock_client_cls.return_value = mock_client
                        mock_backend_cls.return_value = MagicMock()

                        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                            mock_parse.return_value = MagicMock(
                                config=Path("config.yaml"), loglevel=None, mode=None
                            )
                            main()

                        mock_backend_cls.assert_called_once_with(
                            model="gpt-4",
                            api_key="direct-key",
                            base_url=None,
                            timeout=60.0,
                            max_concurrency=1,
                            context_window=128000,
                        )


def test_main_base_url_passthrough() -> None:
    """Test base_url from config is passed to OpenAIBackend."""
    mock_config = _mock_config({"api_key": "test-key", "base_url": "http://localhost:8080/v1"})

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                with patch("little_agent.frontends.build.CliClient") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client.run = AsyncMock(return_value=None)
                    mock_client_cls.return_value = mock_client
                    mock_backend_cls.return_value = MagicMock()

                    with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                        mock_parse.return_value = MagicMock(
                            config=Path("config.yaml"), loglevel=None
                        )
                        main()

                    mock_backend_cls.assert_called_once_with(
                        model="gpt-4",
                        api_key="test-key",
                        base_url="http://localhost:8080/v1",
                        timeout=60.0,
                        max_concurrency=1,
                        context_window=128000,
                    )


def test_build_backend_openai() -> None:
    """Test _build_backend constructs OpenAIBackend correctly."""
    with patch("little_agent.backends.build.OpenAIBackend") as mock_cls:
        mock_cls.return_value = MagicMock()
        _build_backend({"type": "openai", "model": "gpt-4", "api_key": "k"}, "primary")
        mock_cls.assert_called_once_with(
            model="gpt-4",
            api_key="k",
            base_url=None,
            timeout=60.0,
            max_concurrency=1,
            context_window=128000,
        )


def test_build_backend_default_max_concurrency_and_context_window() -> None:
    """Default cfg yields max_concurrency=1 and context_window=128000."""
    with patch("little_agent.backends.build.OpenAIBackend") as mock_cls:
        mock_cls.return_value = MagicMock()
        _build_backend({"type": "openai", "model": "gpt-4", "api_key": "k"}, "primary")
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["max_concurrency"] == 1
        assert kwargs["context_window"] == 128000


def test_build_backend_explicit_max_concurrency_and_context_window() -> None:
    """Explicit max_concurrency and context_window in cfg are passed through."""
    with patch("little_agent.backends.build.OpenAIBackend") as mock_cls:
        mock_cls.return_value = MagicMock()
        _build_backend(
            {
                "type": "openai",
                "model": "gpt-4",
                "api_key": "k",
                "max_concurrency": 4,
                "context_window": 64000,
            },
            "primary",
        )
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["max_concurrency"] == 4
        assert kwargs["context_window"] == 64000


def test_build_backend_unsupported_type_raises() -> None:
    """Test _build_backend raises for unsupported backend type."""
    with pytest.raises(ValueError, match="Unsupported backend type"):
        _build_backend({"type": "foobar", "api_key": "k", "model": "m"}, "primary")


def test_build_backend_missing_type_raises() -> None:
    """Test _build_backend raises when type is missing."""
    with pytest.raises(ValueError, match="must contain a 'type' field"):
        _build_backend({"api_key": "k"}, "primary")


def test_build_backend_missing_model_raises() -> None:
    """Test _build_backend raises when model is missing."""
    with pytest.raises(ValueError, match="must contain a 'model' field"):
        _build_backend({"type": "openai", "api_key": "k"}, "primary")


def test_build_backend_no_api_key_raises() -> None:
    """Test _build_backend raises when API key is not available."""
    with patch("os.environ.get", return_value=None):
        with pytest.raises(ValueError, match="No API key for backend 'primary'"):
            _build_backend({"type": "openai", "api_key_env": "MISSING_KEY"}, "primary")


def _run_main_with_config(mock_config: dict[str, Any]) -> MagicMock:
    """Helper: run main() with given config and return the mock AgentCore call args."""
    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("little_agent.main.AgentCore") as mock_agent_cls:
                    mock_agent = MagicMock()
                    mock_agent_cls.return_value = mock_agent
                    with patch("little_agent.frontends.build.CliClient") as mock_client_cls:
                        mock_client = MagicMock()
                        mock_client.run = AsyncMock(return_value=None)
                        mock_client_cls.return_value = mock_client
                        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                            mock_parse.return_value = MagicMock(
                                config=Path("config.yaml"), loglevel=None, mode=None
                            )
                            main()
                    return mock_agent_cls


def test_main_agent_default_compress_threshold() -> None:
    """Default agent config yields compress_threshold=0.75."""
    mock_config = _mock_config({"api_key": "k"})
    mock_agent_cls = _run_main_with_config(mock_config)
    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["compress_threshold"] == 0.75


def test_main_agent_custom_compress_threshold() -> None:
    """agent.compress_threshold in config is passed to AgentCore."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["agent"] = {"compress_threshold": 0.8}
    mock_agent_cls = _run_main_with_config(mock_config)
    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["compress_threshold"] == pytest.approx(0.8)


def test_main_agent_invalid_compress_threshold_zero_raises() -> None:
    """agent.compress_threshold=0 raises ValueError (must be in (0, 1])."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["agent"] = {"compress_threshold": 0.0}

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(
                        config=Path("config.yaml"), loglevel=None, mode=None
                    )
                    with pytest.raises(ValueError, match="agent.compress_threshold"):  # noqa: E501
                        main()


def test_main_agent_invalid_compress_threshold_above_1_raises() -> None:
    """agent.compress_threshold=1.5 raises ValueError."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["agent"] = {"compress_threshold": 1.5}

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(
                        config=Path("config.yaml"), loglevel=None, mode=None
                    )
                    with pytest.raises(ValueError, match="agent.compress_threshold"):  # noqa: E501
                        main()


def test_main_with_compressor_backend() -> None:
    """Test main constructs compressor backend when present in config."""
    mock_config = {
        "backends": {
            "primary": {"type": "openai", "api_key": "pk", "model": "gpt-4"},
            "compressor": {"type": "openai", "api_key": "ck", "model": "gpt-3.5-turbo"},
        },
        "logging": {"version": 1, "loggers": {"": {"level": "INFO"}}},
        "tools": {"providers": {}},
    }

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                with patch("little_agent.frontends.build.CliClient") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client.run = AsyncMock(return_value=None)
                    mock_client_cls.return_value = mock_client
                    mock_backend_cls.return_value = MagicMock()

                    with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                        mock_parse.return_value = MagicMock(
                            config=Path("config.yaml"), loglevel=None
                        )
                        main()

                    # Both primary and compressor backends are constructed
                    assert mock_backend_cls.call_count == 2


def test_load_permissions_list_builds_chain() -> None:
    """List config with yesman produces a YesManChecker chain."""
    client = MagicMock()
    config = {"permissions": [{"type": "yesman"}]}
    result = _load_permissions(config, client)
    assert isinstance(result, YesManChecker)


def test_load_permissions_dict_warns_and_returns_client() -> None:
    """Dict config (old format) logs a warning and returns client unchanged."""
    client = MagicMock()
    config = {"permissions": {"default": "allow", "rules": []}}
    with patch("little_agent.frontends.build.logger") as mock_logger:
        result = _load_permissions(config, client)
    assert result is client
    mock_logger.warning.assert_called_once()
    assert "old format" in mock_logger.warning.call_args.args[0]


class TestDeepMerge:
    """Unit tests for _deep_merge."""

    def test_deep_merge_scalar_override(self) -> None:
        """Override scalar values replace base values."""
        base = {"a": 1, "b": 2}
        override = {"b": 99}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 99}

    def test_deep_merge_dict_recursive(self) -> None:
        """Nested dicts are merged recursively; base-only keys are preserved."""
        base = {"x": {"keep": True, "overwrite": "old"}}
        override = {"x": {"overwrite": "new", "added": 42}}
        result = _deep_merge(base, override)
        assert result == {"x": {"keep": True, "overwrite": "new", "added": 42}}

    def test_deep_merge_none_override_wins(self) -> None:
        """None in override takes precedence over a dict in base."""
        base = {"compressor": {"keep_turns": 3}}
        override = {"compressor": None}
        result = _deep_merge(base, override)
        assert result["compressor"] is None

    def test_deep_merge_false_override_wins(self) -> None:
        """False in override takes precedence over a dict in base (compressor: false scenario)."""
        base = {"compressor": {"keep_turns": 3}}
        override = {"compressor": False}
        result = _deep_merge(base, override)
        assert result["compressor"] is False

    def test_deep_merge_does_not_mutate_base(self) -> None:
        """Merging does not modify the base dict."""
        base: dict[str, Any] = {"a": {"nested": 1}}
        override: dict[str, Any] = {"a": {"nested": 2, "extra": 3}}
        _deep_merge(base, override)
        assert base == {"a": {"nested": 1}}

    def test_deep_merge_does_not_mutate_override(self) -> None:
        """Merging does not modify the override dict."""
        base: dict[str, Any] = {"a": {"nested": 1, "only_base": True}}
        override: dict[str, Any] = {"a": {"nested": 2}}
        _deep_merge(base, override)
        assert override == {"a": {"nested": 2}}


# ── frontends/build.py ──────────────────────────────────────────────────────


class TestBuildClient:
    def test_build_client_web_explicit_sessions_dir(self) -> None:
        """WebClient is built when frontend.type=web with an explicit sessions_dir."""
        config = {"frontend": {"type": "web", "sessions_dir": "/tmp/test_sessions"}}
        with patch("little_agent.frontends.build.WebClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            client, frontend_type = build_client(config, session_store=None)
        assert frontend_type == "web"
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert "/tmp/test_sessions" in str(kwargs["sessions_dir"])

    def test_build_client_web_default_sessions_dir(self) -> None:
        """WebClient is built with the default sessions_dir when none is specified."""
        config = {"frontend": {"type": "web"}}
        with patch("little_agent.frontends.build.WebClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            client, frontend_type = build_client(config, session_store=None)
        assert frontend_type == "web"
        mock_cls.assert_called_once()

    def test_build_client_acp(self) -> None:
        """AcpClient is built when frontend.type=acp."""
        config = {"frontend": {"type": "acp"}}
        with patch("little_agent.frontends.build.AcpClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            client, frontend_type = build_client(config, session_store=None)
        assert frontend_type == "acp"
        mock_cls.assert_called_once()


class TestBuildHooks:
    def test_build_hooks_deprecated_loggers_key_raises(self) -> None:
        """Legacy loggers: key raises ValueError with migration hint."""
        with pytest.raises(ValueError, match="hooks"):
            build_hooks({"loggers": [{"type": "file"}]})

    def test_build_hooks_none_returns_empty(self) -> None:
        """No hooks: key returns empty list."""
        assert build_hooks({}) == []

    def test_build_hooks_non_list_warns_and_returns_empty(self) -> None:
        """Non-list hooks config logs a warning and returns empty list."""
        with patch("little_agent.frontends.build.logger") as mock_logger:
            result = build_hooks({"hooks": "invalid"})
        assert result == []
        mock_logger.warning.assert_called_once()

    def test_build_hooks_unknown_type_raises(self) -> None:
        """Dict item with any type in hooks: raises ValueError."""
        with pytest.raises(ValueError, match="Unknown hook type"):
            build_hooks({"hooks": [{"type": "file_logger"}]})

    def test_build_hooks_list_with_no_dicts_returns_empty(self) -> None:
        """A hooks list containing only non-dict items returns empty (no valid hooks)."""
        assert build_hooks({"hooks": ["some_string", 42]}) == []


class TestRunFrontend:
    @pytest.mark.asyncio
    async def test_run_frontend_web_default_port(self) -> None:
        """run_frontend calls client.run with default host/port for web."""
        mock_client = AsyncMock()
        mock_agent = MagicMock()
        config: dict[str, Any] = {"frontend": {"type": "web"}}
        await run_frontend(mock_client, mock_agent, config, "web", None)
        mock_client.run.assert_called_once_with(mock_agent, host="127.0.0.1", port=8080)

    @pytest.mark.asyncio
    async def test_run_frontend_web_explicit_host_port(self) -> None:
        """run_frontend passes explicit host and port to client.run for web."""
        mock_client = AsyncMock()
        mock_agent = MagicMock()
        config: dict[str, Any] = {"frontend": {"type": "web", "host": "0.0.0.0", "port": 9090}}
        await run_frontend(mock_client, mock_agent, config, "web", None)
        mock_client.run.assert_called_once_with(mock_agent, host="0.0.0.0", port=9090)

    @pytest.mark.asyncio
    async def test_run_frontend_acp(self) -> None:
        """run_frontend calls client.run(agent) for non-cli, non-web frontend."""
        mock_client = AsyncMock()
        mock_agent = MagicMock()
        await run_frontend(mock_client, mock_agent, {}, "acp", None)
        mock_client.run.assert_called_once_with(mock_agent)


# ── main.py: _ContextFilter / load_config / _load_session_store / _redirect ─


def test_context_filter_injects_fields() -> None:
    """_ContextFilter.filter injects session_id and turn_id from ContextVars."""
    import logging

    from little_agent.agent.context import current_session_id, current_turn_id

    token_s = current_session_id.set("test-session")
    token_t = current_turn_id.set("test-turn")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="",
            args=(),
            exc_info=None,
        )
        f = _ContextFilter()
        result = f.filter(record)
        assert result is True
        assert record.session_id == "test-session"
        assert record.turn_id == "test-turn"
    finally:
        current_session_id.reset(token_s)
        current_turn_id.reset(token_t)


def test_load_config_raises_for_non_mapping(tmp_path: Path) -> None:
    """load_config raises ValueError when YAML is not a mapping."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(bad_yaml)


def test_redirect_acp_logging_stdout_to_stderr() -> None:
    """_redirect_acp_logging redirects stdout handlers and null-stream handlers to stderr."""
    config: dict[str, Any] = {
        "logging": {
            "handlers": {
                "console": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"},
                "null_stream": {"class": "logging.StreamHandler", "stream": None},
            }
        }
    }
    _redirect_acp_logging(config)
    assert config["logging"]["handlers"]["console"]["stream"] == "ext://sys.stderr"
    assert config["logging"]["handlers"]["null_stream"]["stream"] == "ext://sys.stderr"


def test_redirect_acp_logging_explicit_stderr_unchanged() -> None:
    """_redirect_acp_logging leaves handlers already using stderr unchanged."""
    config: dict[str, Any] = {
        "logging": {
            "handlers": {
                "h": {"class": "logging.StreamHandler", "stream": "ext://sys.stderr"},
            }
        }
    }
    _redirect_acp_logging(config)
    assert config["logging"]["handlers"]["h"]["stream"] == "ext://sys.stderr"


def test_load_session_store_explicit_dict_config() -> None:
    """_load_session_store returns a SessionJSONLStore when session_store: is a dict."""
    from little_agent.agent.session_store import SessionJSONLStore

    config: dict[str, Any] = {
        "session_store": {
            "sessions_dir": "/tmp/sessions",
            "filename_template": "{session_id}.jsonl",
        }
    }
    store = _load_session_store(config, "cli", {})
    assert isinstance(store, SessionJSONLStore)


def test_load_session_store_auto_inject_for_web() -> None:
    """_load_session_store auto-creates a store for web frontend with no session_store: key."""
    from little_agent.agent.session_store import SessionJSONLStore

    config: dict[str, Any] = {}  # no session_store key
    store = _load_session_store(config, "web", {})
    assert isinstance(store, SessionJSONLStore)


def test_load_session_store_returns_none_for_cli() -> None:
    """_load_session_store returns None for cli frontend with no session_store: key."""
    config: dict[str, Any] = {}
    store = _load_session_store(config, "cli", {})
    assert store is None


def test_main_memory_key_raises() -> None:
    """Legacy memory: config key raises ValueError with migration hint."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["memory"] = {}

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend"):
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(
                        config=Path("config.yaml"), loglevel=None, mode=None, prompt=None
                    )
                    with pytest.raises(ValueError, match="memory"):
                        main()


def test_main_max_tool_result_chars_zero_raises() -> None:
    """agent.max_tool_result_chars=0 raises ValueError."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["agent"] = {"compress_threshold": 0.75, "max_tool_result_chars": 0}

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(
                        config=Path("config.yaml"), loglevel=None, mode=None, prompt=None
                    )
                    with pytest.raises(ValueError, match="max_tool_result_chars"):
                        main()


def test_main_with_session_store_registers_in_hooks_and_tools() -> None:
    """session_store: config adds the store to both hooks and tools."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["session_store"] = {"sessions_dir": "/tmp/ss"}

    mock_tools = MagicMock()

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("little_agent.main.AgentCore") as mock_agent_cls:
                    mock_agent = MagicMock()
                    mock_agent_cls.return_value = mock_agent
                    with patch("little_agent.frontends.build.CliClient") as mock_client_cls:
                        mock_client = MagicMock()
                        mock_client.run = AsyncMock(return_value=None)
                        mock_client_cls.return_value = mock_client
                        with patch(
                            "little_agent.main.build_tools",
                            return_value=(mock_tools, False),
                        ):
                            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                                mock_parse.return_value = MagicMock(
                                    config=Path("config.yaml"),
                                    loglevel=None,
                                    mode=None,
                                    prompt=None,
                                )
                                main()
                        # session_store should have been registered in tools (line 215)
                        assert mock_tools.register.called


def test_main_mode_override_sets_frontend_type() -> None:
    """--mode acp overrides frontend.type in config."""
    mock_config = _mock_config({"api_key": "k"})

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.backends.build.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("little_agent.frontends.build.AcpClient") as mock_acp_cls:
                    mock_acp = MagicMock()
                    mock_acp.run = AsyncMock(return_value=None)
                    mock_acp_cls.return_value = mock_acp
                    with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                        mock_parse.return_value = MagicMock(
                            config=Path("config.yaml"), loglevel=None, mode="acp", prompt=None
                        )
                        main()
                mock_acp_cls.assert_called_once()
