import logging

from quelware_core.entities.instrument import InstrumentInfo
from quelware_core.entities.resource import (
    ResourceId,
)

logger = logging.getLogger(__name__)


class InstrumentMapper:
    def __init__(self):
        self._id_to_inst_info: dict[ResourceId, InstrumentInfo] = {}

    def add_instrument_info(self, instrument_info: InstrumentInfo):
        self._id_to_inst_info[instrument_info.id] = instrument_info

    def get_instrument_info(self, rid: ResourceId) -> InstrumentInfo:
        return self._id_to_inst_info[rid]

    def build_alias_to_id_map(self) -> dict[str, ResourceId]:
        alias_to_id_map = {}
        for iid, inst_info in self._id_to_inst_info.items():
            alias = inst_info.definition.alias
            if alias in alias_to_id_map:
                logger.warning(
                    "alias `alias` is duplicated."
                    " The items after the first one will be ignored."
                )
                continue
            alias_to_id_map[alias] = iid
        return alias_to_id_map
