import enum
from dataclasses import dataclass, field
from typing import Final

from ..resource import ResourceId


class PortRole(enum.Enum):
    UNSPECIFIED = enum.auto()
    TRANSMITTER = enum.auto()
    TRANSCEIVER = enum.auto()
    RECEIVER = enum.auto()
    UNKNOWN = enum.auto()


@dataclass
class PortInfo:
    id: Final[ResourceId]
    role: PortRole
    depends_on: list[ResourceId] = field(default_factory=list)


__all__ = ["PortInfo", "PortRole"]
