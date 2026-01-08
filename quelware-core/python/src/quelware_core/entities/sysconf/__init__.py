from dataclasses import dataclass

from ..unit import UnitLabel


@dataclass
class UnitConfiguration:
    label: UnitLabel
    macaddress: str
    type: str
    ignored: bool = False
    options: dict[str, str] = {}


@dataclass
class SystemConfiguration:
    units: list[UnitConfiguration]


__all__ = ["SystemConfiguration", "UnitConfiguration"]
