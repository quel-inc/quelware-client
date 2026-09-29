import numpy as np
import pytest

from quelware_tools.diagnostics.pulse_test import (
    TICK_NS,
    Span,
    compare_pulses,
    detect_pulses,
    plan_pulses,
)

_FS_HZ = 2.5e9
_DELAY_NS = 713.3


def _capture(spans: list[Span], *, seed: int = 0) -> np.ndarray:
    """What the monitor would see of ``spans``: a 100 MHz beat, smeared over a
    few samples, delayed and in noise."""
    end_ns = max(s.start_ns + s.length_ns for s in spans) + _DELAY_NS + 2000.0
    t_ns = np.arange(int(end_ns * _FS_HZ / 1e9)) * 1e9 / _FS_HZ
    on = np.zeros(t_ns.size)
    for s in spans:
        on[
            (t_ns >= s.start_ns + _DELAY_NS)
            & (t_ns < s.start_ns + s.length_ns + _DELAY_NS)
        ] = 1
    smeared = np.convolve(on, np.ones(3) / 3, mode="same")
    rng = np.random.default_rng(seed)
    noise = 0.01 * (
        rng.standard_normal(t_ns.size) + 1j * rng.standard_normal(t_ns.size)
    )
    return 0.8 * smeared * np.exp(2j * np.pi * 0.1 * t_ns) + noise


def test_pulses_with_no_gap_between_them_are_expected_as_one() -> None:
    emitted, expected = plan_pulses([4, 8], [0, 32])

    assert len(emitted) == 4
    assert expected[0] == Span(0.0, 8 * TICK_NS)
    assert expected[1].length_ns == pytest.approx(16 * TICK_NS)
    assert len(expected) == 2


def test_the_default_train_is_seen_as_planned() -> None:
    _, expected = plan_pulses(
        [4, 8, 16, 64, 256], [0, 4, 28, 32, 36, 64, 256, 296, 300, 304, 1024]
    )

    measured = detect_pulses(_capture(expected), _FS_HZ)
    matches, extras = compare_pulses(expected, measured, tolerance_ns=2.0)

    assert all(m.ok for m in matches)
    assert extras == []


def test_a_pulse_off_its_place_fails_and_one_missing_fails() -> None:
    _, expected = plan_pulses([16], [64, 64, 64])
    shifted = [expected[0], Span(expected[1].start_ns + 6.4, expected[1].length_ns)]

    matches, extras = compare_pulses(
        expected, detect_pulses(_capture(shifted), _FS_HZ), tolerance_ns=2.0
    )

    assert [m.ok for m in matches] == [True, False, False]
    assert matches[2].measured is None
    assert extras == []


def test_a_pulse_not_planned_is_left_over() -> None:
    _, expected = plan_pulses([16], [64, 256])
    extra = Span(expected[-1].start_ns + 400.0, 16 * TICK_NS)

    matches, extras = compare_pulses(
        expected, detect_pulses(_capture([*expected, extra]), _FS_HZ), tolerance_ns=2.0
    )

    assert all(m.ok for m in matches)
    assert len(extras) == 1
