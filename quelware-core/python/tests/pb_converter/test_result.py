import numpy as np

from quelware_core.entities.result import ResultContainer
from quelware_core.entities.waveform.sampled import IqWaveform
from quelware_core.pb_converter.result import (
    result_container_from_pb,
    result_container_to_pb,
)


def test_result_container_waveforms_roundtrip():
    wave1 = IqWaveform(
        sampling_period_fs=1_000_000,
        iq_array=np.array([1.0 + 1.0j, 0.5 - 0.5j], dtype=np.complex128),
    )
    wave2 = IqWaveform(
        sampling_period_fs=2_000_000,
        iq_array=np.array([0.0 + 0.0j], dtype=np.complex128),
    )

    original = ResultContainer(iq_waveform_result={"readout_0": [wave1, wave2]})

    pb = result_container_to_pb(original)
    recovered = result_container_from_pb(pb)

    assert "readout_0" in recovered.iq_waveform_result
    recovered_waves = recovered.iq_waveform_result["readout_0"]
    assert len(recovered_waves) == 2

    assert recovered_waves[0].sampling_period_fs == 1_000_000
    np.testing.assert_array_equal(recovered_waves[0].iq_array, wave1.iq_array)

    assert recovered_waves[1].sampling_period_fs == 2_000_000
    np.testing.assert_array_equal(recovered_waves[1].iq_array, wave2.iq_array)


def test_result_container_complex_points_roundtrip():
    original_points = [1.0 + 2.0j, -3.0 - 4.0j, 0.0 + 0.0j]

    original = ResultContainer(iq_point_result={"readout_1": original_points})

    pb = result_container_to_pb(original)
    recovered = result_container_from_pb(pb)

    assert "readout_1" in recovered.iq_point_result
    recovered_points = recovered.iq_point_result["readout_1"]

    assert len(recovered_points) == 3
    assert recovered_points == original_points


def test_result_container_integers_roundtrip():
    original_ints = [100, 200, 0, -1]

    original = ResultContainer(integer_result={"counter_0": original_ints})

    pb = result_container_to_pb(original)
    recovered = result_container_from_pb(pb)

    assert "counter_0" in recovered.integer_result
    assert recovered.integer_result["counter_0"] == original_ints


def test_result_container_mixed_roundtrip():
    original = ResultContainer(
        iq_waveform_result={"wave_ch": [IqWaveform(100, np.array([1j]))]},
        iq_point_result={"point_ch": [1 + 1j]},
        integer_result={
            "int_ch": [123],
            "empty_int_ch": [],
        },
    )

    pb = result_container_to_pb(original)
    recovered = result_container_from_pb(pb)

    assert len(recovered.iq_waveform_result["wave_ch"]) == 1
    assert len(recovered.iq_point_result["point_ch"]) == 1
    assert recovered.iq_point_result["point_ch"][0] == 1 + 1j

    assert recovered.integer_result["int_ch"] == [123]
    assert recovered.integer_result["empty_int_ch"] == []
