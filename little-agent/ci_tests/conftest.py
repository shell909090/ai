"""Pytest fixtures for CI integration tests."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from little_agent.main import _DEFAULT_CONFIG, _deep_merge

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


@pytest.fixture(scope="session")
def ci_config(ci_config_path: Path) -> dict[str, Any]:
    """Load CI backend config; skip entire session if config file is missing."""
    if not ci_config_path.exists():
        pytest.skip(f"CI config not found at {ci_config_path}; skipping CI tests")
    with open(ci_config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        pytest.skip(f"CI config at {ci_config_path} is not a YAML mapping")
    return _deep_merge(_DEFAULT_CONFIG, data)
