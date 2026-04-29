"""Frontend client protocol definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from little_agent.types import JSONValue

if TYPE_CHECKING:
    from little_agent.agent.protocol import Session


@dataclass
class SessionUpdate:
    """Represents an update event to the client."""

    type: Literal["agent_message_chunk", "tool_call", "tool_call_update"]
    data: dict[str, JSONValue]


class Client(Protocol):
    """Client protocol for frontend implementations."""

    async def update(self, session: Session, update: SessionUpdate) -> None: ...

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool: ...
