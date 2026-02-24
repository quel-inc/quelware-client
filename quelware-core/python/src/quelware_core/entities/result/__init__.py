from dataclasses import dataclass, field
from typing import TypeAlias

from quelware_core.entities.waveform.sampled import IqPoint, IqWaveform

CaptureWindowName: TypeAlias = str
IqResult: TypeAlias = list[IqWaveform] | list[IqPoint]


@dataclass
class ResultContainer:
    iq_result: dict[CaptureWindowName, IqResult] = field(default_factory=dict)
    integer_result: dict[CaptureWindowName, list[int]] = field(default_factory=dict)
