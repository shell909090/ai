"""Frontend client protocol definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from little_agent.types import JSONValue, SessionUpdate

if TYPE_CHECKING:
    from little_agent.agent.protocol import Session

__all__ = ["Client", "SessionUpdate"]


class Client(Protocol):
    """Client protocol for frontend implementations."""

    async def update(self, session: Session, update: SessionUpdate) -> None: ...

    async def request_permission(
        self,
        session: Session,
        kind: str,
        payload: dict[str, JSONValue],
    ) -> bool: ...
