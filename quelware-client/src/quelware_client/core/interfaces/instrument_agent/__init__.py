from collections.abc import Collection
from typing import Protocol

from quelware_core.entities.clock import CurrentCount, ReferenceCount
from quelware_core.entities.directives import Directive
from quelware_core.entities.instrument import InstrumentStatus
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.session import SessionToken


class InstrumentAgent(Protocol):
    async def get_status(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> InstrumentStatus: ...

    async def configure(
        self, token: SessionToken, resource_id: ResourceId, directive: Directive
    ) -> bool: ...

    async def setup(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
    ) -> bool: ...

    async def get_clock_snapshot(
        self,
    ) -> tuple[CurrentCount, ReferenceCount]: ...

    async def schedule_trigger(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
        target_time: int,
    ) -> bool: ...
    async def fetch_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> ResultContainer: ...


__all__ = ["InstrumentAgent"]
