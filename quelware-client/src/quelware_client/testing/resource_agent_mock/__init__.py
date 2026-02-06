from collections.abc import Collection
from typing import assert_never

from quelware_core.entities.instrument import (
    FixedTimelineConfig,
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.port import PortInfo, PortRole
from quelware_core.entities.resource import ResourceCategory, ResourceId, ResourceInfo

from quelware_client.core.exceptions import (
    ResourceCategoryNotMatchedError,
    ResourceNotFoundError,
)
from quelware_client.core.interfaces.resource_agent import ResourceAgent


def _build_mock_config(definition: InstrumentDefinition):
    match definition.mode:
        case InstrumentMode.FIXED_TIMELINE:
            return FixedTimelineConfig(sampling_period_fs=400_000, bitdepth=16)
        case InstrumentMode.UNSPECIFIED:
            raise ValueError("Unspecified category")
        case _:
            assert_never(definition.mode)


class ResourceAgentMock(ResourceAgent):
    def __init__(self, resource_infos: list[ResourceInfo]):
        self.rsrc_infos = resource_infos
        self.port_id_to_inst_infos: dict[ResourceId, InstrumentInfo] = {}
        self._counter = 0

    async def list_resource_infos(self) -> list[ResourceInfo]:
        return self.rsrc_infos

    async def deploy_instruments(
        self,
        port_id: ResourceId,
        definitions: Collection[InstrumentDefinition],
        append: bool,
    ) -> list[InstrumentInfo]:
        if port_id not in (rinfo.id for rinfo in self.rsrc_infos):
            raise ResourceNotFoundError().with_resource_ids([port_id])
        insts = [
            InstrumentInfo(
                id=ResourceId(f"inst{self._counter}"),
                port_id=port_id,
                definition=d,
                config=_build_mock_config(d),
            )
            for d in definitions
        ]
        return insts

    async def get_port_info(self, resource_id: ResourceId) -> PortInfo:
        port = next(
            PortInfo(ri.id, role=PortRole.TRANSMITTER)
            for ri in self.rsrc_infos
            if ri.id == resource_id
        )
        if not all(
            ri.category == ResourceCategory.PORT
            for ri in self.rsrc_infos
            if port.id == resource_id
        ):
            raise ResourceCategoryNotMatchedError().with_resource_ids([resource_id])
        return port

    async def get_instrument_info(self, resource_id: ResourceId) -> InstrumentInfo:
        port = next(
            PortInfo(ri.id, role=PortRole.TRANSMITTER)
            for ri in self.rsrc_infos
            if ri.id == resource_id
        )
        definition = InstrumentDefinition(
            alias="alias-a",
            mode=InstrumentMode.FIXED_TIMELINE,
            role=InstrumentRole.TRANSMITTER,
            profile=FixedTimelineProfile(
                frequency_range_min=100, frequency_range_max=1000
            ),
        )
        config = FixedTimelineConfig(sampling_period_fs=400_000, bitdepth=16)
        inst = next(
            InstrumentInfo(
                id=ri.id, port_id=port.id, definition=definition, config=config
            )
            for ri in self.rsrc_infos
            if ri.id == resource_id
        )
        if not all(
            ri.category == ResourceCategory.INSTRUMENT
            for ri in self.rsrc_infos
            if port.id == resource_id
        ):
            raise ResourceCategoryNotMatchedError().with_resource_ids([resource_id])
        return inst


__all__ = ["ResourceAgentMock"]
