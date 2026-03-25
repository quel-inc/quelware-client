import enum
from dataclasses import dataclass
from typing import NewType

UnitLabel = NewType("UnitLabel", str)


class UnitStatus(enum.Enum):
    ACTIVE = enum.auto()
    DRAINING = enum.auto()
    RELEASED = enum.auto()
    UNAVAILABLE = enum.auto()
    INITIALIZING = enum.auto()
    MAINTENANCE = enum.auto()


@dataclass
class Unit:
    label: str
    status: UnitStatus
