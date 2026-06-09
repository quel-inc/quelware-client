from quelware_core.entities.clock import CurrentCount, ReferenceCount

from quelware_client.core.interfaces.worker_agent import WorkerAgent


class WorkerAgentMock(WorkerAgent):
    def __init__(self, current_count: int = 1234, reference_count: int = 1000):
        self._current_count = current_count
        self._reference_count = reference_count

    async def get_clock_snapshot(self) -> tuple[CurrentCount, ReferenceCount]:
        return self._current_count, self._reference_count
