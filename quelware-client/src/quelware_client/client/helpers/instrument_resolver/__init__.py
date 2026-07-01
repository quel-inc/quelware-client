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
    """Resolve instrument aliases and ids to their `InstrumentInfo`.

    Maintains a cache of the instruments known to a client, keyed both by
    resource id and by short alias (the part of an alias after the unit
    prefix). Call `refresh()` to populate the cache from a client before
    resolving.
    """

    def __init__(self):
        self._id_to_inst_info: dict[ResourceId, InstrumentInfo] = {}
        self._short_alias_to_ids: dict[str, dict[str, ResourceId]] = {}

    async def refresh(self, client: QuelwareClient):
        """Rebuild the instrument cache from a client.

        Fetches information for every instrument resource the client exposes
        and indexes it by id and by short alias.

        Args:
            client: An initialized client to query.
        """
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
        """Return the cached info for an instrument id.

        Args:
            instrument_id: Full resource id of the instrument.

        Returns:
            The instrument's information.

        Raises:
            ValueError: If the id is not in the cache.
        """
        if instrument_id not in self._id_to_inst_info:
            raise ValueError(f"Instrument with id '{instrument_id}' not found.")
        return self._id_to_inst_info[instrument_id]

    def find_inst_info_by_alias(
        self, alias: str, unit: str | None = None
    ) -> InstrumentInfo:
        """Return the cached info for an instrument alias.

        Args:
            alias: Short alias of the instrument (without the unit prefix).
            unit: Unit label to disambiguate when the alias exists on more
                than one unit.

        Returns:
            The instrument's information.

        Raises:
            ValueError: If the alias is unknown, is missing on ``unit``, or is
                ambiguous and no ``unit`` was given.
        """
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
        """Resolve several instrument aliases to their resource ids.

        Args:
            aliases: Short aliases to resolve.
            unit: Unit label to disambiguate aliases present on multiple units.

        Returns:
            The resource ids, in the same order as ``aliases``.

        Raises:
            ValueError: If any alias is unknown or ambiguous.
        """
        return list(self._resolve_single(alias, unit) for alias in aliases)


__all__ = ["InstrumentResolver"]
