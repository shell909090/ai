"""Shared type definitions."""

from __future__ import annotations

from typing import Literal, Union

JSONScalar = Union[str, int, float, bool, None]
JSONValue = Union[JSONScalar, list["JSONValue"], dict[str, "JSONValue"]]
ContentBlock = dict[str, JSONValue]

StopReason = Literal["end_turn", "cancelled"]
PromptReturn = tuple[StopReason, str]
