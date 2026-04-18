"""Shared pytest fixtures for test_backends package.

The _make_module helper lives in _helpers.py (a regular importable module).
It is re-exported here so conftest also serves as the single source-of-truth
reference, and the make_module fixture below makes it available via pytest
injection when preferred.
"""

from __future__ import annotations

import pytest

from tests.test_backends._helpers import _make_module  # noqa: F401


@pytest.fixture
def make_module():
    """Pytest fixture that exposes _make_module as an injectable helper."""
    return _make_module
