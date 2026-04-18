"""Shared helper utilities for test_backends tests."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any


def _make_module(name: str, **attrs: Any) -> ModuleType:
    """Create a minimal fake module and insert it (plus parent packages) into sys.modules."""
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        key = ".".join(parts[:i])
        if key not in sys.modules:
            mod = ModuleType(key)
            sys.modules[key] = mod
        else:
            mod = sys.modules[key]
    # Set attributes on the leaf module
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod
