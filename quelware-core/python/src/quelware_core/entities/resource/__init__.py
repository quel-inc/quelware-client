import enum
from collections.abc import Collection
from dataclasses import dataclass
from typing import Final, NewType, Protocol

from ..unit import UnitLabel


class ResourceCategory(enum.Enum):
    UNSPECIFIED = enum.auto()
    PORT = enum.auto()
    INSTRUMENT = enum.auto()


ResourceId = NewType("ResourceId", str)


class _ResourceAsField(Protocol):
    id: Final[ResourceId]
    depends_on: list[ResourceId]


class _ResourceAsReadOnlyProperty(Protocol):
    @property
    def id(self) -> ResourceId: ...

    @property
    def depends_on(self) -> list[ResourceId]: ...


type Resource = _ResourceAsField | _ResourceAsReadOnlyProperty


@dataclass
class ResourceInfo:
    id: Final[ResourceId]
    category: ResourceCategory


def get_all_port_ids_from_resource_infos(
    resource_infos: Collection[ResourceInfo],
) -> list[ResourceId]:
    return [ri.id for ri in resource_infos if ri.category is ResourceCategory.PORT]


def get_all_instrument_ids_from_resource_infos(
    resource_infos: Collection[ResourceInfo],
) -> list[ResourceId]:
    return [
        ri.id for ri in resource_infos if ri.category is ResourceCategory.INSTRUMENT
    ]


def extract_unit_label(resource_id: ResourceId) -> UnitLabel:
    return UnitLabel(resource_id.split(":")[0])


__all__ = [
    "Resource",
    "ResourceCategory",
    "ResourceId",
    "ResourceInfo",
    "extract_unit_label",
    "get_all_instrument_ids_from_resource_infos",
    "get_all_port_ids_from_resource_infos",
]
