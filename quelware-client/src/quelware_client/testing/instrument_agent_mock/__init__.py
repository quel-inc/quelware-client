from collections.abc import Collection, Sequence

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
    ) -> bool:
        return True

    async def apply(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
    ) -> bool:
        return True

    async def schedule_trigger(
        self,
        token: SessionToken,
        target_time: int,
    ) -> bool:
        return True

    async def trigger_now(
        self,
        token: SessionToken,
    ) -> int:
        return 1234

    async def fetch_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> ResultContainer:
        return ResultContainer()

    async def wait_for_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
        timeout_sec: float | None,
    ) -> ResultContainer:
        return ResultContainer()


__all__ = ["InstrumentAgentMock"]
