from abc import ABC, abstractmethod
from collections.abc import Collection

from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken


class TriggerAgent(ABC):
    @abstractmethod
    async def trigger(
        self,
        token: SessionToken,
        instrument_ids: Collection[ResourceId],
        requested_min_wait_ms: int | None,
    ) -> int: ...


__all__ = ["TriggerAgent"]
