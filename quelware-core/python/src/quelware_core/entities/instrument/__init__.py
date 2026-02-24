import enum
from dataclasses import dataclass
from typing import Final, Generic, NewType, TypeAlias, TypeVar

from ..resource import ResourceId

InstrumentAlias = NewType("InstrumentAlias", str)


class InstrumentMode(enum.Enum):
    UNSPECIFIED = enum.auto()
    FIXED_TIMELINE = enum.auto()


class InstrumentRole(enum.Enum):
    UNSPECIFIED = enum.auto()
    TRANSMITTER = enum.auto()
    TRANSCEIVER = enum.auto()
    TRANSCEIVER_LOOPBACK = enum.auto()
    RECEIVER = enum.auto()


class InstrumentStatus(enum.Enum):
    UNSPECIFIED = enum.auto()
    UNCONFIGURED = enum.auto()
    READY = enum.auto()
    RUNNING = enum.auto()
    COMPLETED = enum.auto()


class InstrumentLockStatus(enum.Enum):
    UNDEFINED = enum.auto()
    LOCKED = enum.auto()
    UNLOCKED = enum.auto()


@dataclass
class FixedTimelineConfig:
    sampling_period_fs: int
    bitdepth: int


@dataclass
class FixedTimelineProfile:
    frequency_range_min: float
    frequency_range_max: float


ConfigVariant: TypeAlias = FixedTimelineConfig
ProfileVariant: TypeAlias = FixedTimelineProfile

P = TypeVar("P", bound=ProfileVariant)
C = TypeVar("C", bound=ConfigVariant)


@dataclass
class InstrumentDefinition(Generic[P]):
    alias: str
    mode: InstrumentMode
    role: InstrumentRole
    profile: P


@dataclass
class InstrumentInfo(Generic[P, C]):
    id: Final[ResourceId]
    port_id: ResourceId
    definition: InstrumentDefinition[P]
    config: C


__all__ = [
    "ConfigVariant",
    "InstrumentDefinition",
    "InstrumentInfo",
    "InstrumentMode",
    "InstrumentRole",
    "ProfileVariant",
]
