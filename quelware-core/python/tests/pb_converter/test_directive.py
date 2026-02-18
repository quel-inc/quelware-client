import numpy as np

from quelware_core.entities.directives import (
    CaptureWindow,
    SetFixedTimeline,
    SetFrequency,
    WaveformEvent,
)
from quelware_core.entities.waveform.sampled import IqWaveform
from quelware_core.pb_converter.directive import directive_from_pb, directive_to_pb


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
