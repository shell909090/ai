"""Tests for main entry point."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.agent.permissions import YesManChecker
from little_agent.main import (
    _build_backend,
    _load_permissions,
    load_config,
    main,
    setup_logging,
)


def test_setup_logging_default_config() -> None:
    """Test setup_logging uses default config when no config provided."""
    with patch("logging.config.dictConfig") as mock_dict_config:
        setup_logging(None, None)
        assert mock_dict_config.called
        cfg = mock_dict_config.call_args.args[0]
        assert cfg["loggers"][""]["level"] == "INFO"


def test_setup_logging_override_level() -> None:
    """Test setup_logging overrides level via --loglevel."""
    with patch("logging.config.dictConfig") as mock_dict_config:
        setup_logging(None, "DEBUG")
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
                with patch("little_agent.main.OpenAIBackend") as mock_backend_cls:
                    with patch("little_agent.main.CliClient") as mock_client_cls:
                        mock_client = MagicMock()
                        mock_client.run = AsyncMock(return_value=None)
                        mock_client_cls.return_value = mock_client
                        mock_backend_cls.return_value = MagicMock()

                        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                            mock_parse.return_value = MagicMock(
                                config=Path("config.yaml"), loglevel=None
                            )
                            main()

                        mock_client.run.assert_called_once()


def test_main_unsupported_backend_raises() -> None:
    """Test main raises ValueError for unsupported backend type."""
    mock_config = _mock_config({"type": "unsupported"})

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                mock_parse.return_value = MagicMock(config=Path("config.yaml"), loglevel=None)
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
                mock_parse.return_value = MagicMock(config=Path("config.yaml"), loglevel=None)
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
                mock_parse.return_value = MagicMock(config=Path("config.yaml"), loglevel=None)
                with pytest.raises(ValueError, match="'primary'"):
                    main()


def test_main_missing_api_key_raises() -> None:
    """Test main raises ValueError when no API key configured."""
    mock_config = _mock_config({"api_key_env": "MISSING_KEY"})

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("os.environ.get", return_value=None):
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(config=Path("config.yaml"), loglevel=None)
                    with pytest.raises(ValueError, match="No API key for backend 'primary'"):
                        main()


def test_main_api_key_from_config() -> None:
    """Test main uses api_key directly from config."""
    mock_config = _mock_config({"api_key": "direct-key"})
    del mock_config["backends"]["primary"]["api_key_env"]

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.main.OpenAIBackend") as mock_backend_cls:
                with patch("little_agent.main.CliClient") as mock_client_cls:
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
                with patch("little_agent.main.OpenAIBackend") as mock_backend_cls:
                    with patch("little_agent.main.CliClient") as mock_client_cls:
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


def test_main_base_url_passthrough() -> None:
    """Test base_url from config is passed to OpenAIBackend."""
    mock_config = _mock_config({"api_key": "test-key", "base_url": "http://localhost:8080/v1"})

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.main.OpenAIBackend") as mock_backend_cls:
                with patch("little_agent.main.CliClient") as mock_client_cls:
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
    with patch("little_agent.main.OpenAIBackend") as mock_cls:
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
    with patch("little_agent.main.OpenAIBackend") as mock_cls:
        mock_cls.return_value = MagicMock()
        _build_backend({"type": "openai", "model": "gpt-4", "api_key": "k"}, "primary")
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["max_concurrency"] == 1
        assert kwargs["context_window"] == 128000


def test_build_backend_explicit_max_concurrency_and_context_window() -> None:
    """Explicit max_concurrency and context_window in cfg are passed through."""
    with patch("little_agent.main.OpenAIBackend") as mock_cls:
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
            with patch("little_agent.main.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("little_agent.main.AgentCore") as mock_agent_cls:
                    mock_agent = MagicMock()
                    mock_agent_cls.return_value = mock_agent
                    with patch("little_agent.main.CliClient") as mock_client_cls:
                        mock_client = MagicMock()
                        mock_client.run = AsyncMock(return_value=None)
                        mock_client_cls.return_value = mock_client
                        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                            mock_parse.return_value = MagicMock(
                                config=Path("config.yaml"), loglevel=None
                            )
                            main()
                    return mock_agent_cls


def test_main_agent_default_compress_ratio() -> None:
    """Default agent config yields compress_ratio=0.5."""
    mock_config = _mock_config({"api_key": "k"})
    mock_agent_cls = _run_main_with_config(mock_config)
    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["compress_ratio"] == 0.75


def test_main_agent_custom_compress_ratio() -> None:
    """agent.R in config is passed to AgentCore as compress_ratio."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["agent"] = {"R": 0.8}
    mock_agent_cls = _run_main_with_config(mock_config)
    kwargs = mock_agent_cls.call_args.kwargs
    assert kwargs["compress_ratio"] == pytest.approx(0.8)


def test_main_agent_invalid_compress_ratio_zero_raises() -> None:
    """agent.R=0 raises ValueError (must be in (0, 1])."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["agent"] = {"R": 0.0}

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.main.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(config=Path("config.yaml"), loglevel=None)
                    with pytest.raises(ValueError, match="agent.R must be in range"):
                        main()


def test_main_agent_invalid_compress_ratio_above_1_raises() -> None:
    """agent.R=1.5 raises ValueError."""
    mock_config = _mock_config({"api_key": "k"})
    mock_config["agent"] = {"R": 1.5}

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("little_agent.main.OpenAIBackend") as mock_backend_cls:
                mock_backend = MagicMock()
                mock_backend.context_window = 128000
                mock_backend_cls.return_value = mock_backend
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(config=Path("config.yaml"), loglevel=None)
                    with pytest.raises(ValueError, match="agent.R must be in range"):
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
            with patch("little_agent.main.OpenAIBackend") as mock_backend_cls:
                with patch("little_agent.main.CliClient") as mock_client_cls:
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
    with patch("little_agent.main.logger") as mock_logger:
        result = _load_permissions(config, client)
    assert result is client
    mock_logger.warning.assert_called_once()
    assert "old format" in mock_logger.warning.call_args.args[0]
