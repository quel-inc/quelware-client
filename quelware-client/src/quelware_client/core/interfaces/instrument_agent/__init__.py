from collections.abc import Collection, Sequence
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

    async def initialize(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
    ) -> None: ...

    async def configure(
        self,
        token: SessionToken,
        resource_id: ResourceId,
        directives: Sequence[Directive],
    ) -> bool: ...

    async def apply(
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
        target_time: int,
    ) -> bool: ...

    async def fetch_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> ResultContainer: ...


__all__ = ["InstrumentAgent"]
