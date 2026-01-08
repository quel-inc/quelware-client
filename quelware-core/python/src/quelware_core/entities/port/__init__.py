import enum
from dataclasses import dataclass

from ..resource import ResourceId


class PortRole(enum.Enum):
    UNSPECIFIED = enum.auto()
    TRANSMITTER = enum.auto()
    TRANSCEIVER = enum.auto()


@dataclass
class PortInfo:
    id: ResourceId
    role: PortRole


__all__ = ["PortInfo", "PortInfo"]
