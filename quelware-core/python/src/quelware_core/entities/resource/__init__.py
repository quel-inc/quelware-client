import enum
from collections.abc import Collection
from dataclasses import dataclass
from typing import NewType

from ..unit import UnitLabel


class ResourceType(enum.Enum):
    PORT = enum.auto()
    INSTRUMENT = enum.auto()


ResourceId = NewType("ResourceId", str)


@dataclass
class ResourceInfo:
    id: ResourceId
    type: ResourceType


def get_all_port_ids_from_resource_infos(
    resource_infos: Collection[ResourceInfo],
) -> list[ResourceId]:
    return [ri.id for ri in resource_infos if ri.type is ResourceType.PORT]


def get_all_instrument_ids_from_resource_infos(
    resource_infos: Collection[ResourceInfo],
) -> list[ResourceId]:
    return [ri.id for ri in resource_infos if ri.type is ResourceType.INSTRUMENT]


def extract_unit_label(resource_id: ResourceId) -> UnitLabel:
    return UnitLabel(resource_id.split(":")[0])


__all__ = [
    "ResourceId",
    "ResourceInfo",
    "ResourceType",
    "extract_unit_label",
    "get_all_instrument_ids_from_resource_infos",
    "get_all_port_ids_from_resource_infos",
]
