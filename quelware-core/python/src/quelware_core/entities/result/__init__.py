from dataclasses import dataclass, field

from quelware_core.entities.waveform.sampled import IqPoint, IqWaveform

type CaptureWindowName = str
type IqResult = list[IqWaveform] | list[IqPoint]


@dataclass
class ResultContainer:
    iq_result: dict[CaptureWindowName, IqResult] = field(default_factory=dict)
    integer_result: dict[CaptureWindowName, list[int]] = field(default_factory=dict)
