from dataclasses import dataclass, field
from typing import TypeAlias

from quelware_core.entities.waveform.sampled import IqPoint, IqWaveform

CaptureWindowName: TypeAlias = str


@dataclass
class ResultContainer:
    iq_waveform_result: dict[CaptureWindowName, list[IqWaveform]] = field(
        default_factory=dict
    )
    iq_point_result: dict[CaptureWindowName, list[IqPoint]] = field(
        default_factory=dict
    )
    integer_result: dict[CaptureWindowName, list[int]] = field(default_factory=dict)
