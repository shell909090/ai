"""Tests for main entry point."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from little_agent.main import (
    load_config,
    main,
    setup_logging,
)


def test_setup_logging_debug() -> None:
    """Test setup_logging with DEBUG level."""
    with patch("logging.basicConfig") as mock_basic_config:
        setup_logging("DEBUG")
        assert mock_basic_config.called
        assert mock_basic_config.call_args.kwargs["level"] == 10


def test_setup_logging_info() -> None:
    """Test setup_logging with INFO level."""
    with patch("logging.basicConfig") as mock_basic_config:
        setup_logging("INFO")
        assert mock_basic_config.called
        assert mock_basic_config.call_args.kwargs["level"] == 20


def test_setup_logging_default() -> None:
    """Test setup_logging with unknown level defaults to INFO."""
    with patch("logging.basicConfig") as mock_basic_config:
        setup_logging("UNKNOWN")
        assert mock_basic_config.called
        assert mock_basic_config.call_args.kwargs["level"] == 20


def test_load_config() -> None:
    """Test load_config reads YAML file."""
    with patch("builtins.open", MagicMock()):
        with patch("yaml.safe_load", return_value={"backend": {"type": "openai"}}):
            result = load_config(Path("config.yaml"))
            assert result == {"backend": {"type": "openai"}}


def test_main_success() -> None:
    """Test main successful execution."""
    mock_config = {
        "backend": {"type": "openai", "model": "gpt-4", "api_key_env": "OPENAI_API_KEY"},
        "logging": {"level": "INFO"},
        "tools": {"providers": []},
    }

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
                                config=Path("config.yaml"), debug=False
                            )
                            main()

                        mock_client.run.assert_called_once()


def test_main_unsupported_backend_raises() -> None:
    """Test main raises ValueError for unsupported backend."""
    mock_config = {
        "backend": {"type": "unsupported"},
        "logging": {"level": "INFO"},
        "tools": {"providers": []},
    }

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                mock_parse.return_value = MagicMock(config=Path("config.yaml"), debug=False)
                with pytest.raises(ValueError, match="Unsupported backend type"):
                    main()


def test_main_missing_backend_raises() -> None:
    """Test main raises ValueError when backend section is missing."""
    mock_config = {
        "logging": {"level": "INFO"},
        "tools": {"providers": []},
    }

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                mock_parse.return_value = MagicMock(config=Path("config.yaml"), debug=False)
                with pytest.raises(ValueError, match="Config must contain a 'backend' section"):
                    main()


def test_main_missing_backend_type_raises() -> None:
    """Test main raises ValueError when backend type is missing."""
    mock_config = {
        "backend": {"model": "gpt-4"},
        "logging": {"level": "INFO"},
        "tools": {"providers": []},
    }

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                mock_parse.return_value = MagicMock(config=Path("config.yaml"), debug=False)
                with pytest.raises(
                    ValueError, match="Config 'backend' must contain a 'type' field"
                ):
                    main()


def test_main_missing_api_key_raises() -> None:
    """Test main raises ValueError when no API key configured."""
    mock_config = {
        "backend": {"type": "openai", "api_key_env": "MISSING_KEY"},
        "logging": {"level": "INFO"},
        "tools": {"providers": []},
    }

    with patch("little_agent.main.load_config", return_value=mock_config):
        with patch("little_agent.main.setup_logging"):
            with patch("os.environ.get", return_value=None):
                with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                    mock_parse.return_value = MagicMock(config=Path("config.yaml"), debug=False)
                    with pytest.raises(ValueError, match="No API key found"):
                        main()


def test_main_api_key_from_config() -> None:
    """Test main uses api_key directly from config."""
    mock_config = {
        "backend": {"type": "openai", "api_key": "direct-key"},
        "logging": {"level": "INFO"},
        "tools": {"providers": []},
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
                        mock_parse.return_value = MagicMock(config=Path("config.yaml"), debug=False)
                        main()

                    mock_backend_cls.assert_called_once_with(
                        model="gpt-4", api_key="direct-key", base_url=None
                    )


def test_main_api_key_priority_over_env() -> None:
    """Test config api_key takes priority over api_key_env."""
    mock_config = {
        "backend": {
            "type": "openai",
            "api_key": "direct-key",
            "api_key_env": "OPENAI_API_KEY",
        },
        "logging": {"level": "INFO"},
        "tools": {"providers": []},
    }

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
                                config=Path("config.yaml"), debug=False
                            )
                            main()

                        mock_backend_cls.assert_called_once_with(
                            model="gpt-4", api_key="direct-key", base_url=None
                        )


def test_main_base_url_passthrough() -> None:
    """Test base_url from config is passed to OpenAIBackend."""
    mock_config = {
        "backend": {
            "type": "openai",
            "api_key": "test-key",
            "base_url": "http://localhost:8080/v1",
        },
        "logging": {"level": "INFO"},
        "tools": {"providers": []},
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
                        mock_parse.return_value = MagicMock(config=Path("config.yaml"), debug=False)
                        main()

                    mock_backend_cls.assert_called_once_with(
                        model="gpt-4",
                        api_key="test-key",
                        base_url="http://localhost:8080/v1",
                    )
