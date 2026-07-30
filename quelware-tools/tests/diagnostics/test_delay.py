import numpy as np
import pytest

from quelware_tools.diagnostics._delay import find_pulse_chunks, measure_delay

_SAMPLE_RATE_HZ = 500e6
_N = 4096


def _pulse(
    delay_samples: int, length_samples: int, noise: float, seed: int = 0
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    iq = noise * (rng.standard_normal(_N) + 1j * rng.standard_normal(_N))
    iq[delay_samples : delay_samples + length_samples] += 1.0 + 0.0j
    return iq


def test_measures_pulse_delay():
    iq = _pulse(delay_samples=300, length_samples=50, noise=0.01)
    res = measure_delay(iq, _SAMPLE_RATE_HZ)
    assert res.detected
    assert abs(res.delay_samples - 300) <= 1.0
    expected_ns = 300 / _SAMPLE_RATE_HZ * 1e9
    assert abs(res.delay_ns - expected_ns) <= 1e9 / _SAMPLE_RATE_HZ


def test_delay_survives_constant_lo_leakage():
    iq = _pulse(delay_samples=300, length_samples=50, noise=0.01) + (5.0 + 5.0j)
    res = measure_delay(iq, _SAMPLE_RATE_HZ)
    assert res.detected
    assert abs(res.delay_samples - 300) <= 1.0


def test_pure_noise_is_not_detected():
    rng = np.random.default_rng(1)
    iq = 0.01 * (rng.standard_normal(_N) + 1j * rng.standard_normal(_N))
    res = measure_delay(iq, _SAMPLE_RATE_HZ)
    assert not res.detected


def test_first_pulse_wins_when_several_present():
    iq = _pulse(delay_samples=300, length_samples=50, noise=0.01)
    iq[900:950] += 1.0 + 0.0j
    res = measure_delay(iq, _SAMPLE_RATE_HZ)
    assert res.detected
    assert abs(res.delay_samples - 300) <= 1.0


def test_short_blips_are_dropped_as_noise():
    mag = np.zeros(200)
    mag[50] = 1.0  # single-sample spike, below minimal_length
    mag[100:120] = 1.0  # a real 20-sample run
    chunks = find_pulse_chunks(mag, threshold=0.5, minimal_length=4)
    assert chunks == [(100, 120)]


def test_empty_iq_raises():
    with pytest.raises(ValueError):
        measure_delay(np.array([], dtype=complex), _SAMPLE_RATE_HZ)
