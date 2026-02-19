from collections.abc import Collection

from quelware_core.entities.clock import CurrentCount, ReferenceCount
from quelware_core.entities.directives import Directive
from quelware_core.entities.instrument import InstrumentStatus
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken

from quelware_client.core.interfaces.instrument_agent import (
    InstrumentAgent,
    ResultContainer,
)


class InstrumentAgentMock(InstrumentAgent):
    async def get_status(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> InstrumentStatus:
        return InstrumentStatus.UNCONFIGURED

    async def configure(
        self, token: SessionToken, resource_id: ResourceId, directive: Directive
    ) -> bool:
        return True

    async def setup(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
    ) -> bool:
        return True

    async def get_clock_snapshot(
        self,
    ) -> tuple[CurrentCount, ReferenceCount]:
        return 1234, 1000

    async def schedule_trigger(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
        target_time: int,
    ) -> bool:
        return True

    async def fetch_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> ResultContainer:
        return ResultContainer()


__all__ = ["InstrumentAgentMock"]
