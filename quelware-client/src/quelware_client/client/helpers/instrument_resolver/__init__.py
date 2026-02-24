import logging
from asyncio import TaskGroup

from quelware_core.entities.instrument import InstrumentInfo
from quelware_core.entities.resource import (
    ResourceCategory,
    ResourceId,
)

from quelware_client.core import QuelwareClient

logger = logging.getLogger(__name__)


class InstrumentResolver:
    def __init__(self):
        self._id_to_inst_info: dict[ResourceId, InstrumentInfo] = {}
        self._alias_to_id: dict[str, ResourceId] = {}

    async def refresh(self, client: QuelwareClient):
        resource_infos = list(
            rinfo
            for rinfo in await client.list_resource_infos()
            if rinfo.category is ResourceCategory.INSTRUMENT
        )
        tasks = []
        async with TaskGroup() as tg:
            for rinfo in resource_infos:
                tasks.append(tg.create_task(client.get_instrument_info(rinfo.id)))
        inst_infos: list[InstrumentInfo] = []
        for t in tasks:
            inst_infos.append(t.result())

        new_id_to_inst_info = {}
        new_alias_to_id = {}
        for inst_info in inst_infos:
            new_id_to_inst_info[inst_info.id] = inst_info
            new_alias_to_id[inst_info.definition.alias] = inst_info.id

        self._id_to_inst_info = new_id_to_inst_info
        self._alias_to_id = new_alias_to_id
        logger.info(f"{len(self._id_to_inst_info)} instruments has been registered.")

    def find_inst_info_by_id(self, instrument_id: ResourceId) -> InstrumentInfo:
        if instrument_id not in self._id_to_inst_info:
            raise ValueError(f"Instrument with id '{instrument_id}' not found.")
        return self._id_to_inst_info[instrument_id]

    def find_inst_info_by_alias(self, alias: str) -> InstrumentInfo:
        return self.find_inst_info_by_id(self._resolve_single(alias))

    def _resolve_single(self, alias) -> ResourceId:
        if alias not in self._alias_to_id:
            raise ValueError(f"Instrument with alias '{alias}' not found.")
        return self._alias_to_id[alias]

    def resolve(self, aliases: list[str]) -> list[ResourceId]:
        return list(self._resolve_single(alias) for alias in aliases)


__all__ = ["InstrumentResolver"]
