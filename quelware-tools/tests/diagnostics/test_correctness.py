from dataclasses import replace

import numpy as np
import pytest

from quelware_tools.diagnostics.correctness import Judge, Record, Tolerance, judge
from quelware_tools.diagnostics.shots import Pulse, Shape, Shot, Window, to_samples

_PERIOD_NS = 0.8
# as tight as a noiseless loopback allows
_TOLERANCE = Tolerance(
    gain_rel=0.01,
    phase_deg=1.0,
    position_samples=1,
    repeat_rel=1e-6,
    quiet_rel=0.01,
    noise_rel=0.0,
)
_SHOT = Shot(
    pulses=(
        Pulse(100.0),
        Pulse(700.0, gain=0.5, phase_deg=90.0, shape=Shape("gauss", 160.0)),
        Pulse(4000.0, gain=0.8, phase_deg=-45.0, shape=Shape("ramp", 240.0)),
    ),
    windows=(Window("a", 0.0, 2400.0), Window("b", 3800.0, 1600.0)),
)


def _loopback(
    shot: Shot,
    *,
    delay_ns: float = 320.0,
    gain: complex = 0.7 * np.exp(0.5j),
    apply_phase_offset: bool = True,
) -> dict[str, np.ndarray]:
    """What a faithful loopback returns for the shot."""
    turn = np.exp(1j * np.radians(shot.phase_offset_deg or 0.0))
    delay = to_samples(delay_ns, _PERIOD_NS)
    captures = {}
    for w in shot.windows:
        start = to_samples(w.start_ns, _PERIOD_NS)
        capture = np.zeros(to_samples(w.length_ns, _PERIOD_NS), dtype=complex)
        for p in shot.pulses:
            samples = p.shape.samples(_PERIOD_NS)
            wave = gain * p.gain * np.exp(1j * np.radians(p.phase_deg))
            if apply_phase_offset:
                wave *= turn
            at = to_samples(p.start_ns, _PERIOD_NS) + delay - start
            lo, hi = max(at, 0), min(at + len(samples), len(capture))
            if lo < hi:
                capture[lo:hi] += wave * samples[lo - at : hi - at]
        captures[w.name] = capture
    return captures


def _record(shot: Shot = _SHOT, **kwargs) -> Record:
    return Record("u:loopback", _PERIOD_NS, shot, _loopback(shot, **kwargs))


def _one_line(found: list[str]) -> str:
    assert len(found) == 1, found
    return found[0]


def test_a_faithful_loopback_passes_whatever_its_delay_and_gain():
    assert judge([_record(delay_ns=0.0, gain=1.0)], _TOLERANCE) == []
    assert judge([_record(delay_ns=640.0, gain=0.01j)], _TOLERANCE) == []


def test_a_pulse_that_comes_back_weaker_is_named():
    rec = _record()
    rec.captures["b"] *= 0.9

    assert "pulse 2 at 4000 ns in window b came back at 0.9 of the gain sent" in (
        _one_line(judge([rec], _TOLERANCE))
    )


def test_a_pulse_that_comes_back_turned_is_named():
    rec = _record()
    rec.captures["b"] *= np.exp(1j * np.radians(10.0))

    assert "pulse 2 at 4000 ns in window b came back turned 10.0 deg" in _one_line(
        judge([rec], _TOLERANCE)
    )


def test_a_pulse_that_comes_back_elsewhere_is_named():
    rec = _record()
    rec.captures["b"] = np.roll(rec.captures["b"], 5)

    assert "pulse 2 at 4000 ns in window b came back 5 samples off" in "\n".join(
        judge([rec], _TOLERANCE)
    )


def test_a_pulse_that_does_not_come_back_is_named():
    rec = _record()
    rec.captures["b"][:] = 0.0

    assert "pulse 2 at 4000 ns in window b came back at 0 of the gain sent" in (
        "\n".join(judge([rec], _TOLERANCE))
    )


def test_what_an_earlier_output_left_where_nothing_was_sent_is_found():
    rec = _record()
    rec.captures["a"][100:300] += 0.2

    assert "window a holds 0.286 of full scale at 80 ns into it" in _one_line(
        judge([rec], _TOLERANCE)
    )


@pytest.mark.parametrize(("iterations", "allowed"), [(1, True), (100, False)])
def test_noise_where_nothing_was_sent_is_allowed_as_one_iteration_leaves_it(
    iterations: int, allowed: bool
):
    """Averaging N iterations lowers noise by sqrt(N), so the same noise left in an
    average of many is something else."""
    tolerance = replace(_TOLERANCE, quiet_rel=0.05, noise_rel=0.1)
    shot = replace(_SHOT, iterations=iterations)
    rec = _record(shot, gain=1.0)
    rec.captures["a"][2800] += 0.08

    assert (judge([rec], tolerance) == []) is allowed


def test_a_window_of_another_length_than_declared_is_named():
    rec = _record()
    rec.captures["a"] = rec.captures["a"][:-8]

    assert "window a returned 2992 samples, not 3000" in "\n".join(
        judge([rec], _TOLERANCE)
    )


def test_shots_on_one_loopback_share_its_delay():
    later = replace(
        _SHOT,
        pulses=tuple(replace(p, start_ns=p.start_ns + 64.0) for p in _SHOT.pulses),
    )

    assert judge([_record(), _record(later)], _TOLERANCE) == []
    assert "shot 1 came back 8 samples later than shot 0" in _one_line(
        judge([_record(), _record(later, delay_ns=320.0 + 6.4)], _TOLERANCE)
    )


def test_a_phase_offset_that_is_not_applied_turns_the_loopback_between_shots():
    turned = replace(_SHOT, phase_offset_deg=90.0)

    assert judge([_record(), _record(turned)], _TOLERANCE) == []
    assert "shot 1 came back turned -90.0 deg from shot 0" in _one_line(
        judge([_record(), _record(turned, apply_phase_offset=False)], _TOLERANCE)
    )


def test_the_same_shot_fired_again_returns_the_same_capture():
    again = _record()
    again.captures["a"] = again.captures["a"] * (1 + 1e-3)

    assert judge([_record(), _record()], _TOLERANCE) == []
    assert "shot 1 differs from shot 0, the same shot, by 0.000" in "\n".join(
        judge([_record(), again], _TOLERANCE)
    )


def test_a_judge_of_many_shots_need_not_keep_their_captures():
    again = _record()
    again.captures["a"] = again.captures["a"] * (1 + 1e-3)
    judge_ = Judge(_TOLERANCE, keep_captures=False)

    assert judge_.check(_record()) == []
    assert judge_.check(again) == []


def test_every_iteration_of_a_raw_capture_is_returned():
    raw = replace(_SHOT, raw=True, iterations=3)
    captures = {n: np.stack([c] * 3) for n, c in _loopback(raw).items()}
    short = {n: c[:2] for n, c in captures.items()}

    assert judge([Record("u:loopback", _PERIOD_NS, raw, captures)], _TOLERANCE) == []
    assert "window a returned 2 iterations, not 3" in "\n".join(
        judge([Record("u:loopback", _PERIOD_NS, raw, short)], _TOLERANCE)
    )


def test_a_pulse_sent_after_the_last_window_is_left_out():
    late = replace(_SHOT, pulses=(*_SHOT.pulses, Pulse(9000.0)))

    assert judge([_record(late)], _TOLERANCE) == []


def test_a_pulse_too_short_to_measure_is_not_judged_by_itself():
    """Its edges are all there is of it; it still counts where nothing is sent."""
    short = replace(
        _SHOT, pulses=(*_SHOT.pulses, Pulse(1500.0, shape=Shape("rect", 12.8)))
    )
    rec = _record(short)
    at = to_samples(1500.0 + 320.0, _PERIOD_NS)
    rec.captures["a"][at : at + 16] *= 0.5

    assert judge([rec], _TOLERANCE) == []


def test_a_pulse_with_no_silence_around_it_is_judged_on_all_but_its_position():
    """Back to back, its neighbours match it as well a few samples off."""
    train = replace(
        _SHOT,
        pulses=(
            Pulse(100.0),
            Pulse(300.0, gain=0.6, phase_deg=40.0),
            Pulse(500.0, gain=0.8, phase_deg=-70.0),
            Pulse(4000.0),
        ),
    )
    rec = _record(train)
    middle = to_samples(300.0 + 320.0, _PERIOD_NS)
    rec.captures["a"][middle : middle + 250] *= np.exp(1j * np.radians(10.0))

    found = "\n".join(judge([rec], _TOLERANCE))
    assert "pulse 1 at 300 ns in window a came back turned 10.0 deg" in found
    assert "samples off" not in found


_PATHS = {"tx_p02": (160.0, 0.3 - 0.2j), "trx_p00p01": (480.0, 0.05j)}
_FROM_TWO = Shot(
    pulses=(
        Pulse(100.0, source="tx_p02"),
        Pulse(400.0, gain=0.5, phase_deg=30.0, source="tx_p02"),
        Pulse(3000.0, gain=0.7, source="trx_p00p01", shape=Shape("gauss", 160.0)),
        Pulse(3400.0, phase_deg=-60.0, source="trx_p00p01"),
    ),
    windows=(Window("a", 0.0, 1600.0), Window("b", 2800.0, 2000.0)),
)


def _monitor_capture(shot: Shot) -> dict[str, np.ndarray]:
    """Each port's pulses along a path of its own, summed as the monitor gets them."""
    total: dict[str, np.ndarray] = {}
    for source, (delay_ns, gain) in _PATHS.items():
        own = replace(shot, pulses=tuple(p for p in shot.pulses if p.source == source))
        for name, capture in _loopback(own, delay_ns=delay_ns, gain=gain).items():
            total[name] = total.get(name, 0) + capture
    return total


def test_each_port_is_judged_along_its_own_path():
    rec = Record("u:monitor", _PERIOD_NS, _FROM_TWO, _monitor_capture(_FROM_TWO))

    assert judge([rec], _TOLERANCE) == []


def test_a_pulse_from_one_port_that_comes_back_weaker_is_named_with_its_port():
    captures = _monitor_capture(_FROM_TWO)
    captures["b"][1300:] *= 0.8
    rec = Record("u:monitor", _PERIOD_NS, _FROM_TWO, captures)

    assert "pulse 3 from trx_p00p01 at 3400 ns in window b came back at" in (
        "\n".join(judge([rec], _TOLERANCE))
    )
    assert "tx_p02" not in "\n".join(judge([rec], _TOLERANCE))


@pytest.mark.parametrize("kind", ["rect", "gauss", "ramp"])
def test_a_shape_is_as_long_as_declared_and_peaks_at_full_scale(kind):
    samples = Shape(kind, 160.0).samples(_PERIOD_NS)

    assert len(samples) == 200
    assert np.abs(samples).max() == pytest.approx(1.0, abs=0.01)
