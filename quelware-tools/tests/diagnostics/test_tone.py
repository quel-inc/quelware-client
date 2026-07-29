import numpy as np
import pytest

from quelware_tools.diagnostics._tone import detect_tone

_SAMPLE_RATE_HZ = 500e6
_N = 4096
_BIN_HZ = _SAMPLE_RATE_HZ / _N


def _tone(freq_hz: float, noise: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(_N) / _SAMPLE_RATE_HZ
    signal = np.exp(2j * np.pi * freq_hz * t)
    noise_iq = noise * (rng.standard_normal(_N) + 1j * rng.standard_normal(_N))
    return signal + noise_iq


def test_detects_clean_tone():
    iq = _tone(10e6, noise=0.01)
    res = detect_tone(
        iq,
        _SAMPLE_RATE_HZ,
        expected_hz=10e6,
        freq_tol_hz=2 * _BIN_HZ,
        min_peak_to_median_db=20.0,
    )
    assert res.ok
    assert abs(res.measured_hz - 10e6) <= 2 * _BIN_HZ


def test_pure_noise_is_below_threshold():
    rng = np.random.default_rng(1)
    iq = rng.standard_normal(_N) + 1j * rng.standard_normal(_N)
    res = detect_tone(
        iq,
        _SAMPLE_RATE_HZ,
        expected_hz=10e6,
        freq_tol_hz=2 * _BIN_HZ,
        min_peak_to_median_db=20.0,
    )
    assert not res.above_threshold
    assert not res.ok


def test_tone_at_wrong_frequency_fails_tolerance():
    iq = _tone(10e6, noise=0.01)
    res = detect_tone(
        iq,
        _SAMPLE_RATE_HZ,
        expected_hz=50e6,
        freq_tol_hz=2 * _BIN_HZ,
        min_peak_to_median_db=20.0,
    )
    assert res.above_threshold
    assert not res.within_tolerance
    assert not res.ok


def test_empty_iq_raises():
    with pytest.raises(ValueError):
        detect_tone(
            np.array([], dtype=complex),
            _SAMPLE_RATE_HZ,
            expected_hz=0.0,
            freq_tol_hz=1.0,
            min_peak_to_median_db=1.0,
        )
