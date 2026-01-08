from abc import ABC, abstractmethod
from collections.abc import Collection

from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken


class SessionAgent(ABC):
    @abstractmethod
    async def open_session(
        self,
        resource_ids: Collection[ResourceId],
        tentative_ttl_ms: int,
        committed_ttl_ms: int,
    ) -> tuple[SessionToken, list[ResourceId]]: ...

    @abstractmethod
    async def close_session(self, token: SessionToken) -> bool: ...


__all__ = ["SessionAgent"]
