from quelware_core.entities.unit import UnitLabel, UnitStatus

from quelware_client.core.interfaces.system_configuration_agent import (
    SystemConfigurationAgent,
)


class SystemConfigurationAgentMock(SystemConfigurationAgent):
    def __init__(self, unit_to_status: dict[UnitLabel, UnitStatus]):
        self._unit_to_status = unit_to_status

    async def list_active_units(self) -> list[UnitLabel]:
        return list(
            ul
            for ul, status in self._unit_to_status.items()
            if status is UnitStatus.ACTIVE
        )


__all__ = ["SystemConfigurationAgentMock"]
