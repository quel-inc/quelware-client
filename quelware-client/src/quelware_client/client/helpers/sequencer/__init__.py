from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from quelware_core.entities.directives import (
    CaptureWindow,
    SetFixedTimeline,
    WaveformEvent,
)
from quelware_core.entities.waveform.sampled import IqArray, IqWaveform


@dataclass
class _SequencerEvent:
    waveform_name: str
    start_offset_ns: float
    gain: float
    phase_offset_deg: float


@dataclass
class _SequencerCaptureWindow:
    name: str
    start_offset_ns: float
    length_ns: float


@dataclass
class _Waveform:
    sampling_period_ns: float
    iq_array: IqArray


class Sequencer:
    def __init__(self, default_sampling_period_ns: float):
        self._waveform_library: dict[str, _Waveform] = {}
        self._alias_to_events: dict[str, list[_SequencerEvent]] = defaultdict(list)
        self._alias_to_capwin: dict[str, list[_SequencerCaptureWindow]] = defaultdict(
            list
        )
        self._length_ns: float = 0
        self._default_sampling_period_ns: float = default_sampling_period_ns

    def register_waveform(
        self,
        name: str,
        waveform: npt.ArrayLike,
        sampling_period_ns: float | None = None,
    ):
        if sampling_period_ns is None:
            sampling_period_ns = self._default_sampling_period_ns
        if np.any(np.abs(waveform) > 1):
            raise ValueError("The amplitude must be in the range -1 to 1.")
        self._waveform_library[name] = _Waveform(
            sampling_period_ns=sampling_period_ns,
            iq_array=np.array(waveform, dtype=complex),
        )

    def add_event(
        self,
        instrument_alias: str,
        waveform_name: str,
        start_offset_ns: float,
        gain: float = 1.0,
        phase_offset_deg: float = 0.0,
    ):
        if waveform_name not in self._waveform_library:
            raise ValueError(f"waveform '{waveform_name}' is not registered.")
        event = _SequencerEvent(
            waveform_name=waveform_name,
            start_offset_ns=start_offset_ns,
            gain=gain,
            phase_offset_deg=phase_offset_deg,
        )
        self._alias_to_events[instrument_alias].append(event)

        waveform = self._waveform_library[waveform_name]
        end_at_ns = (
            start_offset_ns + len(waveform.iq_array) * waveform.sampling_period_ns
        )
        self._length_ns = max(self._length_ns, end_at_ns)

    def add_capture_window(
        self,
        instrument_alias: str,
        window_name: str,
        start_offset_ns: float,
        length_ns: float,
    ):
        capwin = _SequencerCaptureWindow(
            name=window_name,
            start_offset_ns=start_offset_ns,
            length_ns=length_ns,
        )
        self._alias_to_capwin[instrument_alias].append(capwin)

        end_at_ns = start_offset_ns + length_ns
        self._length_ns = max(self._length_ns, end_at_ns)

    @property
    def length_ns(self) -> float:
        return self._length_ns

    def export_set_fixed_timeline_directive(
        self, instrument_alias: str, sampling_period_fs: int
    ) -> SetFixedTimeline:
        name_to_index: dict[str, int] = {}
        counter = 0
        local_library: list[IqWaveform] = []
        local_events: list[WaveformEvent] = []

        for event in self._alias_to_events[instrument_alias]:
            if event.waveform_name in name_to_index:
                index = name_to_index[event.waveform_name]
            else:
                waveform = self._waveform_library[event.waveform_name]
                local_library.append(
                    IqWaveform(
                        sampling_period_fs=round(waveform.sampling_period_ns * 1e6),
                        iq_array=waveform.iq_array,
                    )
                )
                index = counter
                name_to_index[event.waveform_name] = index
                counter += 1

            start_offset_samples = round(
                event.start_offset_ns * 1e6 / sampling_period_fs
            )
            local_events.append(
                WaveformEvent(
                    waveform_index=index,
                    start_offset_samples=start_offset_samples,
                    gain=event.gain,
                    phase_offset_deg=event.phase_offset_deg,
                )
            )

        local_capwins: list[CaptureWindow] = []
        for capwin in self._alias_to_capwin[instrument_alias]:
            local_capwins.append(
                CaptureWindow(
                    name=capwin.name,
                    start_offset_samples=round(
                        capwin.start_offset_ns * 1e6 / sampling_period_fs
                    ),
                    length_samples=round(capwin.length_ns * 1e6 / sampling_period_fs),
                )
            )

        length_sample = round(self.length_ns * 1e6 / sampling_period_fs)
        return SetFixedTimeline(
            waveform_library=local_library,
            events=local_events,
            capture_windows=local_capwins,
            length=length_sample,
        )


__all__ = ["Sequencer"]
