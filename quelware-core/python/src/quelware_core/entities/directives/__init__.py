from collections.abc import Sequence
from dataclasses import dataclass
from typing import Never

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


type WaveformLibrary = Sequence[IqWaveform]


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


type FixedTimelineDirective = (
    SetFrequency | SetPhaseOffset | SetTimingOffset | SetFixedTimeline | SetLoop
)

type AnotherModeDirective = Never

type Directive = FixedTimelineDirective | AnotherModeDirective
