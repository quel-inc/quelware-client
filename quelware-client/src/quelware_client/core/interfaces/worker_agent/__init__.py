from typing import Protocol

from quelware_core.entities.clock import CurrentCount, ReferenceCount


class WorkerAgent(Protocol):
    async def get_clock_snapshot(self) -> tuple[CurrentCount, ReferenceCount]: ...
