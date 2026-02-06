import numpy as np
import pytest
from quelware_core.entities.directives import SetFixedTimeline

from quelware_client.client.helpers.sequencer import Sequencer


def test_register_waveform_validation():
    seq = Sequencer(default_sampling_period_ns=1.0)

    seq.register_waveform("valid", np.array([0.5, 0.5j, -0.5, -0.5j]))
    assert "valid" in seq._waveform_library

    with pytest.raises(ValueError, match="amplitude must be in the range"):
        seq.register_waveform("invalid", np.array([1.1, 0.0]))


def test_add_event_unregistered_waveform():
    seq = Sequencer(default_sampling_period_ns=1.0)
    with pytest.raises(ValueError, match="is not registered"):
        seq.add_event("alias", "missing", start_offset_ns=0.0)


def test_sequencer_length_calculation():
    seq = Sequencer(default_sampling_period_ns=2.0)
    seq.register_waveform("wf1", np.array([1.0, 1.0, 1.0]))

    assert seq.length_ns == 0.0

    # 3 samples * 2.0 ns = 6.0 ns duration
    seq.add_event("inst1", "wf1", start_offset_ns=4.0)
    assert seq.length_ns == 10.0

    seq.add_capture_window("inst1", "cap1", start_offset_ns=5.0, length_ns=20.0)
    assert seq.length_ns == 25.0


def test_export_directive_timing_and_indexing():
    seq = Sequencer(default_sampling_period_ns=1.0)

    seq.register_waveform("wf_a", np.array([0.5, 0.5]), sampling_period_ns=2.0)
    seq.register_waveform("wf_b", np.array([0.1]))

    seq.add_event("inst1", "wf_a", start_offset_ns=2.0, gain=0.8, phase_offset_deg=90)
    seq.add_event("inst1", "wf_b", start_offset_ns=10.0)
    seq.add_event("inst1", "wf_a", start_offset_ns=20.0)

    seq.add_capture_window("inst1", "cap1", start_offset_ns=30.0, length_ns=10.0)

    # hardware sampling rate: 500,000 fs = 0.5 ns / sample
    directive = seq.export_set_fixed_timeline_directive(
        instrument_alias="inst1", sampling_period_fs=500_000
    )

    assert isinstance(directive, SetFixedTimeline)

    # Ensure waveforms are deduplicated in the library
    assert len(directive.waveform_library) == 2

    assert len(directive.events) == 3

    # First event (wf_a -> index 0)
    # 2.0 ns / 0.5 ns = 4 samples
    assert directive.events[0].waveform_index == 0
    assert directive.events[0].start_offset_samples == 4
    assert directive.events[0].gain == 0.8
    assert directive.events[0].phase_offset_deg == 90.0

    # Second event (wf_b -> index 1)
    # 10.0 ns / 0.5 ns = 20 samples
    assert directive.events[1].waveform_index == 1
    assert directive.events[1].start_offset_samples == 20

    # Third event (wf_a reused -> index 0)
    # 20.0 ns / 0.5 ns = 40 samples
    assert directive.events[2].waveform_index == 0
    assert directive.events[2].start_offset_samples == 40

    assert len(directive.capture_windows) == 1
    assert directive.capture_windows[0].name == "cap1"
    assert directive.capture_windows[0].start_offset_samples == 60  # 30.0 / 0.5
    assert directive.capture_windows[0].length_samples == 20  # 10.0 / 0.5

    # seq.length_ns is 40.0 ns (end of cap1) -> 40.0 / 0.5 = 80 samples
    assert directive.length == 80
