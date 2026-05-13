"""Shared scalar/JSON type definitions used across all layers."""

from __future__ import annotations

JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
ContentBlock = dict[str, JSONValue]
