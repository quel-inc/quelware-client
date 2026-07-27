from dataclasses import dataclass


@dataclass(frozen=True)
class UnitControlSpec:
    key: str
    allowed_values: tuple[str, ...]
    current_value: str


@dataclass(frozen=True)
class UnitConfiguration:
    supported: tuple[UnitControlSpec, ...]

    def values(self) -> dict[str, str]:
        return {spec.key: spec.current_value for spec in self.supported}


__all__ = ["UnitConfiguration", "UnitControlSpec"]
