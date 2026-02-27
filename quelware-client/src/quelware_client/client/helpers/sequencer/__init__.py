import logging
import math
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

logger = logging.getLogger(__name__)


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


@dataclass
class _AliasBinding:
    sampling_period_fs: int
    step_samples: int


class Sequencer:
    def __init__(
        self, default_sampling_period_ns: float, enforce_sample_grid: bool = True
    ):
        self._waveform_library: dict[str, _Waveform] = {}
        self._alias_to_events: dict[str, list[_SequencerEvent]] = defaultdict(list)
        self._alias_to_capwin: dict[str, list[_SequencerCaptureWindow]] = defaultdict(
            list
        )

        self._default_sampling_period_ns: float = default_sampling_period_ns
        self._iterations: int = 1

        self._bindings: dict[str, _AliasBinding] = {}
        self._enforce_sample_grid: bool = enforce_sample_grid
        self._length_ns: float = 0.0

    def bind(self, alias: str, sampling_period_fs: int, step_samples: int):
        self._bindings[alias] = _AliasBinding(
            sampling_period_fs=sampling_period_fs,
            step_samples=step_samples,
        )

    def _check_and_convert_to_samples(
        self, alias: str, time_ns: float, name_for_log: str
    ) -> int:
        if alias not in self._bindings:
            raise ValueError(
                f"Alias '{alias}' is not bound to the sequencer. Call bind() first."
            )

        period_fs = self._bindings[alias].sampling_period_fs
        time_fs = time_ns * 1e6
        samples = time_fs / period_fs
        rounded_samples = round(samples)

        if abs(samples - rounded_samples) > 0.001:
            msg = (
                f"{name_for_log} ({time_ns} ns) is not a multiple of sampling period "
                f"({period_fs} fs) for alias '{alias}'. Calculated samples: {samples}"
            )
            if self._enforce_sample_grid:
                raise ValueError(msg)
            else:
                logger.warning(f"{msg}. Rounding to {rounded_samples} samples.")

        return rounded_samples

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

        self._check_and_convert_to_samples(
            instrument_alias, start_offset_ns, "Event start_offset_ns"
        )

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
        self._check_and_convert_to_samples(
            instrument_alias,
            start_offset_ns,
            f"Capture window '{window_name}' start_offset_ns",
        )
        self._check_and_convert_to_samples(
            instrument_alias, length_ns, f"Capture window '{window_name}' length_ns"
        )

        capwin = _SequencerCaptureWindow(
            name=window_name,
            start_offset_ns=start_offset_ns,
            length_ns=length_ns,
        )
        self._alias_to_capwin[instrument_alias].append(capwin)
        end_at_ns = start_offset_ns + length_ns
        self._length_ns = max(self._length_ns, end_at_ns)

    def extend_length_ns(self, additional_ns: float):
        self._length_ns += additional_ns

    def set_iterations(self, iterations: int):
        self._iterations = iterations

    @property
    def aligned_length_fs(self) -> int:
        if not self._bindings:
            return math.ceil(self._length_ns * 1e6)

        lcm_step_fs = 1
        for b in self._bindings.values():
            step_fs = b.sampling_period_fs * b.step_samples
            lcm_step_fs = math.lcm(lcm_step_fs, step_fs)

        length_fs = math.ceil(self._length_ns * 1e6)
        remainder = length_fs % lcm_step_fs
        if remainder != 0:
            length_fs += lcm_step_fs - remainder
        return length_fs

    def export_set_fixed_timeline_directive(
        self, instrument_alias: str
    ) -> SetFixedTimeline:
        if instrument_alias not in self._bindings:
            raise ValueError(f"Alias '{instrument_alias}' is not bound.")

        sampling_period_fs = self._bindings[instrument_alias].sampling_period_fs

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

            start_offset_samples = self._check_and_convert_to_samples(
                instrument_alias, event.start_offset_ns, "Export event"
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
                    start_offset_samples=self._check_and_convert_to_samples(
                        instrument_alias, capwin.start_offset_ns, "Export capwin start"
                    ),
                    length_samples=self._check_and_convert_to_samples(
                        instrument_alias, capwin.length_ns, "Export capwin length"
                    ),
                )
            )

        length_sample = (
            self.aligned_length_fs + sampling_period_fs - 1
        ) // sampling_period_fs

        return SetFixedTimeline(
            waveform_library=local_library,
            events=local_events,
            capture_windows=local_capwins,
            length=length_sample,
            iterations=self._iterations,
        )
