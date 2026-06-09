from collections.abc import Collection

from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken

from quelware_client.core.interfaces.trigger_agent import TriggerAgent


class TriggerAgentMock(TriggerAgent):
    def __init__(self, scheduled_clock_count: int = 1234):
        self._scheduled = scheduled_clock_count
        self.calls: list[tuple[SessionToken, list[ResourceId], int | None]] = []

    async def trigger(
        self,
        token: SessionToken,
        instrument_ids: Collection[ResourceId],
        requested_min_wait_ms: int | None,
    ) -> int:
        self.calls.append((token, list(instrument_ids), requested_min_wait_ms))
        return self._scheduled


__all__ = ["TriggerAgentMock"]
