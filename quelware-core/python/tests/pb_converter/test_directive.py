import struct

import numpy as np
import pytest

import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.directives import (
    CaptureWindow,
    SetFixedTimeline,
    SetFrequency,
    WaveformEvent,
)
from quelware_core.entities.waveform.sampled import IqWaveform
from quelware_core.pb_converter.directive import (
    directive_from_pb,
    directive_to_pb,
    iq_waveform_from_dense_pb,
    iq_waveform_to_dense_pb,
)


def test_set_frequency_roundtrip():
    original = SetFrequency(hz=5.2e9)
    pb = directive_to_pb(original)
    recovered = directive_from_pb(pb)

    assert isinstance(recovered, SetFrequency)
    assert recovered.hz == 5.2e9


def test_set_fixed_timeline_roundtrip():
    original = SetFixedTimeline(
        waveform_library=[
            IqWaveform(
                sampling_period_fs=1000, iq_array=np.array([1.0 + 2.0j, -0.5 - 1.5j])
            )
        ],
        events=[
            WaveformEvent(
                waveform_index=0,
                start_offset_samples=10,
                gain=0.5,
                phase_offset_deg=90.0,
            )
        ],
        capture_windows=[
            CaptureWindow(name="cap1", start_offset_samples=20, length_samples=100)
        ],
        length=200,
        iterations=4,
    )

    pb = directive_to_pb(original)
    recovered = directive_from_pb(pb)

    assert isinstance(recovered, SetFixedTimeline)
    assert recovered.length == 200

    assert len(recovered.waveform_library) == 1
    np.testing.assert_array_equal(
        recovered.waveform_library[0].iq_array, original.waveform_library[0].iq_array
    )
    assert recovered.waveform_library[0].sampling_period_fs == 1000

    assert len(recovered.events) == 1
    assert recovered.events[0].waveform_index == 0
    assert recovered.events[0].start_offset_samples == 10
    assert recovered.events[0].gain == 0.5
    assert recovered.events[0].phase_offset_deg == 90.0

    assert len(recovered.capture_windows) == 1
    assert recovered.capture_windows[0].name == "cap1"
    assert recovered.capture_windows[0].start_offset_samples == 20
    assert recovered.capture_windows[0].length_samples == 100


def test_iq_waveform_dense_golden_bytes():
    wave = IqWaveform(
        sampling_period_fs=500_000,
        iq_array=np.array([1.0 + 2.0j, -0.5 + 0.25j], dtype=np.complex128),
    )

    pb = iq_waveform_to_dense_pb(wave)

    assert pb.dtype == pb_models.DenseIqArrayDtype.COMPLEX128_LE_INTERLEAVED
    assert pb.sample_count == 2
    assert pb.sampling_period_fs == 500_000
    # (i, q) interleaved float64 little-endian, built independently of numpy
    assert pb.data == struct.pack("<4d", 1.0, 2.0, -0.5, 0.25)

    recovered = iq_waveform_from_dense_pb(pb)
    assert recovered.sampling_period_fs == 500_000
    np.testing.assert_array_equal(recovered.iq_array, wave.iq_array)


def test_iq_waveform_dense_rejects_length_mismatch():
    pb = pb_models.DenseIqArray(
        dtype=pb_models.DenseIqArrayDtype.COMPLEX128_LE_INTERLEAVED,
        sample_count=2,
        sampling_period_fs=1_000_000,
        data=b"\x00" * 24,
    )

    with pytest.raises(ValueError, match="does not match"):
        iq_waveform_from_dense_pb(pb)


def test_iq_waveform_dense_rejects_unknown_dtype():
    pb = pb_models.DenseIqArray(
        dtype=pb_models.DenseIqArrayDtype.UNSPECIFIED,
        sample_count=1,
        sampling_period_fs=1_000_000,
        data=b"\x00" * 16,
    )

    with pytest.raises(ValueError, match="dtype"):
        iq_waveform_from_dense_pb(pb)
