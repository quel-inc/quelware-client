from collections.abc import Mapping
from typing import Protocol

from quelware_core.entities.clock import CurrentCount, ReferenceCount
from quelware_core.entities.session import SessionToken

from quelware_client.core.unit_control import UnitConfiguration


class WorkerAgent(Protocol):
    async def get_clock_snapshot(self) -> tuple[CurrentCount, ReferenceCount]: ...

    async def get_unit_configuration(self) -> UnitConfiguration: ...

    async def configure_unit(
        self, controls: Mapping[str, str], session_token: SessionToken
    ) -> dict[str, str]: ...
