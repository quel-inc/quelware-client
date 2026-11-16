"""What a shot sends and captures, in nanoseconds, whatever the sampling period."""

from dataclasses import dataclass
from typing import Literal, TypeAlias

import numpy as np

PULSE_NS = 200.0

Kind: TypeAlias = Literal["rect", "gauss", "ramp"]
KINDS: tuple[Kind, ...] = ("rect", "gauss", "ramp")


@dataclass(frozen=True)
class Shape:
    """A pulse's envelope at unit amplitude."""

    kind: Kind = "rect"
    length_ns: float = PULSE_NS

    def samples(self, period_ns: float) -> np.ndarray:
        n = to_samples(self.length_ns, period_ns)
        match self.kind:
            case "rect":
                envelope = np.ones(n)
            case "gauss":
                t = np.arange(n) - (n - 1) / 2
                envelope = np.exp(-0.5 * (t / (n / 6)) ** 2)
            case "ramp":
                envelope = np.linspace(0.2, 1.0, n)
        return envelope.astype(complex)


@dataclass(frozen=True)
class Pulse:
    start_ns: float
    gain: float = 1.0
    phase_deg: float = 0.0
    shape: Shape = Shape()
    # the port it is sent from; "" when the capturing instrument sends it itself
    source: str = ""


@dataclass(frozen=True)
class Window:
    name: str
    start_ns: float
    length_ns: float


@dataclass(frozen=True)
class Shot:
    """Pulses sent and windows captured from the start of each iteration."""

    pulses: tuple[Pulse, ...]
    windows: tuple[Window, ...]
    iterations: int = 100
    # silence after the last pulse or window, before the next iteration
    gap_ns: float = 10_000.0
    phase_offset_deg: float | None = None
    # every iteration's waveform, rather than their average
    raw: bool = False
    label: str = ""


def to_samples(ns: float, period_ns: float) -> int:
    return round(ns / period_ns)


def on_grid(ns: float, period_ns: float) -> float:
    """The time nearest to `ns` that falls on a sample."""
    return to_samples(ns, period_ns) * period_ns


__all__ = [
    "KINDS",
    "PULSE_NS",
    "Kind",
    "Pulse",
    "Shape",
    "Shot",
    "Window",
    "on_grid",
    "to_samples",
]
