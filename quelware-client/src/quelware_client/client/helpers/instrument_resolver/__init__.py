import asyncio
import logging

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
        self._short_alias_to_ids: dict[str, dict[str, ResourceId]] = {}

    async def refresh(self, client: QuelwareClient):
        resource_infos = list(
            rinfo
            for rinfo in await client.list_resource_infos()
            if rinfo.category is ResourceCategory.INSTRUMENT
        )

        coros = [client.get_instrument_info(rinfo.id) for rinfo in resource_infos]

        inst_infos: list[InstrumentInfo] = await asyncio.gather(*coros)

        new_id_to_inst_info: dict[ResourceId, InstrumentInfo] = {}
        new_short: dict[str, dict[str, ResourceId]] = {}
        for inst_info in inst_infos:
            full_alias = inst_info.definition.alias
            new_id_to_inst_info[inst_info.id] = inst_info
            unit, _, short = full_alias.partition(":")
            if short:
                new_short.setdefault(short, {})[unit] = inst_info.id
            else:
                new_short.setdefault(full_alias, {})[""] = inst_info.id

        self._id_to_inst_info = new_id_to_inst_info
        self._short_alias_to_ids = new_short
        logger.info(f"{len(self._id_to_inst_info)} instruments has been registered.")

    def find_inst_info_by_id(self, instrument_id: ResourceId) -> InstrumentInfo:
        if instrument_id not in self._id_to_inst_info:
            raise ValueError(f"Instrument with id '{instrument_id}' not found.")
        return self._id_to_inst_info[instrument_id]

    def find_inst_info_by_alias(
        self, alias: str, unit: str | None = None
    ) -> InstrumentInfo:
        return self.find_inst_info_by_id(self._resolve_single(alias, unit))

    def _resolve_single(self, alias: str, unit: str | None = None) -> ResourceId:
        if alias not in self._short_alias_to_ids:
            raise ValueError(f"Instrument with alias '{alias}' not found.")
        unit_map = self._short_alias_to_ids[alias]
        if unit is not None:
            if unit not in unit_map:
                raise ValueError(
                    f"Instrument with alias '{alias}' not found in unit '{unit}'."
                )
            return unit_map[unit]
        if len(unit_map) > 1:
            raise ValueError(
                f"Multiple instruments match alias '{alias}' "
                f"(units: {list(unit_map.keys())}). Specify unit to disambiguate."
            )
        return next(iter(unit_map.values()))

    def resolve(self, aliases: list[str], unit: str | None = None) -> list[ResourceId]:
        return list(self._resolve_single(alias, unit) for alias in aliases)


__all__ = ["InstrumentResolver"]
