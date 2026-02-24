import enum
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

from typing_extensions import Never

from quelware_core.entities.waveform.sampled import IqWaveform


@dataclass
class SetFrequency:
    hz: float


@dataclass
class SetPhaseOffset:
    degree: float


@dataclass
class SetTimingOffset:
    offset_samples: int


@dataclass
class SetLoop:
    loop_count: int


class CaptureMode(enum.Enum):
    UNSPECIFIED = enum.auto()
    RAW_WAVEFORMS = enum.auto()
    AVERAGED_WAVEFORM = enum.auto()
    AVERAGED_VALUE = enum.auto()
    VALUES_PER_LOOP = enum.auto()


@dataclass
class SetCaptureMode:
    mode: CaptureMode


WaveformLibrary: TypeAlias = Sequence[IqWaveform]


@dataclass
class WaveformEvent:
    waveform_index: int
    start_offset_samples: int
    gain: float
    phase_offset_deg: float


@dataclass
class CaptureWindow:
    name: str
    start_offset_samples: int
    length_samples: int


@dataclass
class SetFixedTimeline:
    waveform_library: WaveformLibrary
    events: list[WaveformEvent]
    capture_windows: list[CaptureWindow]
    length: int


FixedTimelineDirective: TypeAlias = (
    SetFrequency
    | SetPhaseOffset
    | SetTimingOffset
    | SetFixedTimeline
    | SetLoop
    | SetCaptureMode
)

AnotherModeDirective: TypeAlias = Never

Directive: TypeAlias = FixedTimelineDirective | AnotherModeDirective
