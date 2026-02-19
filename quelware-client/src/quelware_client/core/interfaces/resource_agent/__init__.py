from collections.abc import Collection
from typing import Protocol

from quelware_core.entities.instrument import (
    InstrumentDefinition,
    InstrumentInfo,
    ProfileVariant,
)
from quelware_core.entities.port import PortInfo
from quelware_core.entities.resource import ResourceId, ResourceInfo
from quelware_core.entities.session import SessionToken


class ResourceAgent(Protocol):
    async def list_resource_infos(self) -> list[ResourceInfo]: ...

    async def deploy_instruments(
        self,
        port_id: ResourceId,
        definitions: Collection[InstrumentDefinition[ProfileVariant]],
        append: bool,
        session_token: SessionToken,
    ) -> list[InstrumentInfo]: ...

    async def get_port_info(self, resource_id: ResourceId) -> PortInfo: ...

    async def get_instrument_info(self, resource_id: ResourceId) -> InstrumentInfo: ...


__all__ = ["ResourceAgent"]
