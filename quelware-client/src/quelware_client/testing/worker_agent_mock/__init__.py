from collections.abc import Mapping

from quelware_core.entities.clock import CurrentCount, ReferenceCount
from quelware_core.entities.session import SessionToken

from quelware_client.core.interfaces.worker_agent import WorkerAgent
from quelware_client.core.unit_control import UnitConfiguration


class WorkerAgentMock(WorkerAgent):
    def __init__(
        self,
        current_count: int = 1234,
        reference_count: int = 1000,
        unit_configuration: UnitConfiguration | None = None,
    ):
        self._current_count = current_count
        self._reference_count = reference_count
        self._unit_configuration = unit_configuration or UnitConfiguration(supported=())
        self.configure_calls: list[dict[str, str]] = []

    async def get_clock_snapshot(self) -> tuple[CurrentCount, ReferenceCount]:
        return self._current_count, self._reference_count

    async def get_unit_configuration(self) -> UnitConfiguration:
        return self._unit_configuration

    async def configure_unit(
        self, controls: Mapping[str, str], session_token: SessionToken
    ) -> dict[str, str]:
        self.configure_calls.append(dict(controls))
        return dict(controls)
