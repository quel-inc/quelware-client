import numpy as np
import pytest

from quelware_tools.diagnostics._delay import (
    comb_plan,
    find_pulse_chunks,
    measure_delay,
    verify_comb,
)

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


def test_comb_plan_deskews_onto_a_clean_grid():
    # delays span 700..1300 ns; t_ref rounds max up to 2000 ns.
    plan = comb_plan(
        [700.0, 1300.0, 900.0], round_ns=1000.0, pulse_ns=100.0, blank_ns=100.0
    )
    assert plan.t_ref_ns == 2000.0
    assert plan.period_ns == 200.0
    assert plan.arrivals_ns == (2000.0, 2200.0, 2400.0)
    # emit offset = arrival - own delay; all non-negative since t_ref >= max delay.
    assert plan.emit_offsets_ns == (1300.0, 900.0, 1500.0)
    assert all(o >= 0 for o in plan.emit_offsets_ns)


def _comb_capture(
    arrivals_ns, sample_rate_hz, pulse_ns=100.0, noise=0.01, amplitudes=None, seed=0
):
    ns_per_sample = 1e9 / sample_rate_hz
    total = int((max(arrivals_ns) + 500.0) / ns_per_sample)
    rng = np.random.default_rng(seed)
    iq = noise * (rng.standard_normal(total) + 1j * rng.standard_normal(total))
    width = int(pulse_ns / ns_per_sample)
    if amplitudes is None:
        amplitudes = [1.0] * len(arrivals_ns)
    for a, amp in zip(arrivals_ns, amplitudes, strict=True):
        start = int(round(a / ns_per_sample))
        iq[start : start + width] += amp + 0.0j
    return iq


def test_verify_comb_passes_when_pulses_land_on_grid():
    arrivals = (2000.0, 2200.0, 2400.0)
    iq = _comb_capture(arrivals, _SAMPLE_RATE_HZ)
    matches = verify_comb(iq, _SAMPLE_RATE_HZ, arrivals, tolerance_samples=2.0)
    assert [m.ok for m in matches] == [True, True, True]
    assert all(
        m.deviation_samples is not None and abs(m.deviation_samples) <= 2.0
        for m in matches
    )


def test_verify_comb_finds_weak_pulse_beside_strong():
    # a per-window threshold keeps the weak middle pulse from being lost next to
    # the strong ones (a global-peak threshold would miss it).
    arrivals = (2000.0, 2200.0, 2400.0)
    iq = _comb_capture(arrivals, _SAMPLE_RATE_HZ, amplitudes=[1.0, 0.15, 1.0])
    matches = verify_comb(iq, _SAMPLE_RATE_HZ, arrivals, tolerance_samples=2.0)
    assert [m.ok for m in matches] == [True, True, True]


def test_verify_comb_guard_window_ignores_strong_neighbor_tail():
    # A strong pulse's fall tail bleeds toward the next (weak) slot; a wide window
    # latches onto that tail, but the guard window (half the blank gap) excludes it.
    ns_per_sample = 1e9 / _SAMPLE_RATE_HZ
    arrivals = (2000.0, 2200.0)
    total = int(2800.0 / ns_per_sample)
    rng = np.random.default_rng(3)
    iq = 0.01 * (rng.standard_normal(total) + 1j * rng.standard_normal(total))
    width = int(100.0 / ns_per_sample)
    s0 = int(2000.0 / ns_per_sample)
    iq[s0 : s0 + width] += 1.0  # strong slot-0 pulse
    iq[s0 + width : s0 + 2 * width] += np.exp(-np.arange(width) / 8.0)  # its fall tail
    s1 = int(2200.0 / ns_per_sample)
    iq[s1 : s1 + width] += 0.1  # weak slot-1 pulse

    guard = verify_comb(iq, _SAMPLE_RATE_HZ, arrivals, search_radius_ns=50.0)
    assert [m.ok for m in guard] == [True, True]
    dev = guard[1].deviation_samples
    assert dev is not None and abs(dev) <= 2.0

    wide = verify_comb(iq, _SAMPLE_RATE_HZ, arrivals, search_radius_ns=100.0)
    assert not wide[1].ok  # wide window mistakes the neighbor tail for the pulse


def test_verify_comb_flags_a_shifted_pulse():
    arrivals = (2000.0, 2200.0, 2400.0)
    # move the middle pulse 40 ns (20 samples @500 MHz) late.
    iq = _comb_capture((2000.0, 2240.0, 2400.0), _SAMPLE_RATE_HZ)
    matches = verify_comb(iq, _SAMPLE_RATE_HZ, arrivals, tolerance_samples=2.0)
    assert [m.ok for m in matches] == [True, False, True]


def test_verify_comb_flags_a_missing_pulse():
    arrivals = (2000.0, 2200.0, 2400.0)
    iq = _comb_capture((2000.0, 2400.0), _SAMPLE_RATE_HZ)  # middle slot empty
    matches = verify_comb(iq, _SAMPLE_RATE_HZ, arrivals, tolerance_samples=2.0)
    assert matches[1].measured_ns is None
    assert [m.ok for m in matches] == [True, False, True]
