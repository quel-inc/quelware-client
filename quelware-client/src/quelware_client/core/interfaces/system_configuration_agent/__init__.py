from abc import ABC, abstractmethod

from quelware_core.entities.unit import UnitLabel


class SystemConfigurationAgent(ABC):
    @abstractmethod
    async def list_active_units(self) -> list[UnitLabel]: ...


__all__ = ["SystemConfigurationAgent"]
