from dataclasses import dataclass, field
from enum import Enum

import dacite


class ClockUnitType(Enum):
    UNKNOWN = "UNKNOWN"
    GENERATOR = "GENERATOR"
    RELAY = "RELAY"


class ControlUnitType(Enum):
    UNKNOWN = "UNKNOWN"
    QUEL3 = "QUEL3"


class MiscellaneousUnitType(Enum):
    UNKNOWN = "UNKNOWN"
    PLC = "PLC"
    NETWORK_SWITCH = "NETWORK_SWITCH"


@dataclass
class GatewayServer:
    name: str
    ipaddress: str = ""


@dataclass
class ClockUnit:
    name: str
    macaddress: str
    ipaddress: str
    type: ClockUnitType = ClockUnitType.UNKNOWN


@dataclass
class ControlUnit:
    name: str
    macaddress: str
    ipaddress: str
    type: ControlUnitType = ControlUnitType.UNKNOWN
    options: dict[str, str] = field(default_factory=dict)
    ignored: bool = False


@dataclass
class MiscellaneousUnit:
    name: str = ""
    type: MiscellaneousUnitType = MiscellaneousUnitType.UNKNOWN
    macaddress: str = ""
    ipaddress: str = ""


@dataclass
class SystemConfiguration:
    version: int = 0
    gateway_server: GatewayServer | None = None
    clock_units: list[ClockUnit] = field(default_factory=list)
    control_units: list[ControlUnit] = field(default_factory=list)
    miscellaneous_units: list[MiscellaneousUnit] = field(default_factory=list)


def sysconf_from_dict(dic) -> SystemConfiguration:
    return dacite.from_dict(
        data_class=SystemConfiguration,
        data=dic,
        config=dacite.Config(
            cast=[ClockUnitType, ControlUnitType, MiscellaneousUnitType]
        ),
    )


__all__ = [
    "ClockUnit",
    "ClockUnitType",
    "ControlUnit",
    "ControlUnitType",
    "GatewayServer",
    "MiscellaneousUnit",
    "MiscellaneousUnitType",
    "SystemConfiguration",
    "sysconf_from_dict",
]
