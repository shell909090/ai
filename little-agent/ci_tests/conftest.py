"""Pytest fixtures for CI integration tests."""

from pathlib import Path

import pytest

_DEFAULT_CI_CONFIG = str(Path.home() / ".config" / "little_agent" / "config.yaml")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --ci-config option for CI integration test config path."""
    parser.addoption(
        "--ci-config",
        default=_DEFAULT_CI_CONFIG,
        help="Path to config.yaml for CI integration tests",
    )


@pytest.fixture(scope="session")
def ci_config_path(request: pytest.FixtureRequest) -> Path:
    """Return the CI config file path from --ci-config option."""
    return Path(request.config.getoption("--ci-config")).expanduser()
