import numpy as np
import pytest
from quelware_core.entities.directives import SetFixedTimeline

from quelware_client.client.helpers.sequencer import Sequencer


def test_waveform_amplitude_validation():
    seq = Sequencer(default_sampling_period_ns=1.0)

    valid_waveform = np.array([0.5, 0.5j, -0.5, -0.5j])
    seq.register_waveform("valid_pulse", valid_waveform)

    assert "valid_pulse" in seq._waveform_library

    invalid_waveform = np.array([1.1, 0.0])
    with pytest.raises(ValueError, match="amplitude must be in the range"):
        seq.register_waveform("invalid_pulse", invalid_waveform)


def test_enforce_sample_grid_rejects_unaligned_offsets():
    seq = Sequencer(default_sampling_period_ns=1.0, enforce_sample_grid=True)

    seq.bind("inst1", sampling_period_fs=2_000_000, step_samples=4)
    seq.register_waveform("pulse", np.array([1.0]))

    with pytest.raises(ValueError, match="not a multiple of sampling period"):
        seq.add_event("inst1", "pulse", start_offset_ns=3.0)


def test_timeline_alignment_pads_to_lcm_step_samples():
    seq = Sequencer(default_sampling_period_ns=1.0)

    seq.bind("inst1", sampling_period_fs=500_000, step_samples=16)

    seq.register_waveform("pulse_a", np.array([0.5, 0.5]), sampling_period_ns=2.0)
    seq.register_waveform("pulse_b", np.array([0.1]))

    seq.add_event(
        "inst1", "pulse_a", start_offset_ns=2.0, gain=0.8, phase_offset_deg=90
    )
    seq.add_event("inst1", "pulse_b", start_offset_ns=10.0)

    seq.add_capture_window("inst1", "cap_window", start_offset_ns=30.0, length_ns=10.0)

    seq.extend_length_ns(5.0)

    directive = seq.export_set_fixed_timeline_directive("inst1")

    assert isinstance(directive, SetFixedTimeline)
    assert len(directive.waveform_library) == 2
    assert len(directive.events) == 2

    first_event = directive.events[0]
    assert first_event.waveform_index == 0
    assert first_event.start_offset_samples == 4
    assert first_event.gain == 0.8
    assert first_event.phase_offset_deg == 90.0

    first_window = directive.capture_windows[0]
    assert first_window.name == "cap_window"
    assert first_window.start_offset_samples == 60

    # Total duration before padding: 30.0ns + 10.0ns + 5.0ns = 45.0ns
    # Hardware step constraint: 0.5ns * 16 samples = 8.0ns
    # Padded duration: ceil(45.0 / 8.0) * 8.0 = 48.0ns
    # Padded samples: 48.0ns / 0.5ns = 96
    expected_padded_samples = 96
    assert directive.length == expected_padded_samples
