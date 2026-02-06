from dataclasses import dataclass

from quelware_core.entities.waveform.sampled import IqWaveform

type CaptureWindowName = str


@dataclass
class FixedTimelineResult:
    iq_datas: dict[CaptureWindowName, list[IqWaveform]]


type ResultVariant = FixedTimelineResult


@dataclass
class ResultContainer:
    fixed_timeline: FixedTimelineResult | None = None


def result_extractor_fixed_timeline(container: ResultContainer) -> FixedTimelineResult:
    if container.fixed_timeline is not None:
        return container.fixed_timeline
    raise ValueError("Result not available.")
