"""Whether what came back is what was sent, judged from the shots alone.

Each port a shot sends from reaches the capture along a path whose delay and gain are
not known, so each path's are estimated from all of its pulses at once, and every pulse
is then held to what was sent for it: its gain, its phase, its position. Between the
pulses a capture holds nothing but noise. Shots captured on one instrument share its
paths, so they share their delays and gains, and the same shot fired again returns the
same capture.
"""

from dataclasses import dataclass
from typing import TypeAlias

import numpy as np

from .shots import Pulse, Shot, to_samples

# the part of a pulse its gain and phase are measured on, leaving out its edges
EDGE_NS = 20.0
# how far from a pulse a capture is held to hold nothing, past its edges' ringing
QUIET_GUARD_NS = 60.0


@dataclass(frozen=True)
class Tolerance:
    """How closely a capture has to follow what was sent; the defaults hold a box."""

    # a tx port's path to the monitor returns pulses near full scale up to 15 % lower
    gain_rel: float = 0.2
    phase_deg: float = 3.0
    position_samples: int = 8
    repeat_rel: float = 0.1
    # how much of full scale a capture may hold where nothing was sent
    quiet_rel: float = 0.05
    # the noise one iteration leaves there, which averaging N lowers by sqrt(N)
    noise_rel: float = 0.1
    # the longest a path may take to return what was sent
    delay_max_ns: float = 1000.0


DEFAULT_TOLERANCE = Tolerance()


@dataclass
class Record:
    """A shot as fired, the instrument that captured it, and each window's capture:
    one waveform, or one per iteration for a raw shot."""

    instrument: str
    period_ns: float
    shot: Shot
    captures: dict[str, np.ndarray]


@dataclass(frozen=True)
class _Fit:
    delay: int
    gain: complex


class Judge:
    """Judges shots one after another, each against what was sent for it and against
    the earlier shots along the same paths."""

    def __init__(
        self, tolerance: Tolerance = DEFAULT_TOLERANCE, *, keep_captures: bool = True
    ):
        """`keep_captures` keeps each distinct shot's capture, to compare with the same
        shot fired again; a judge of many distinct shots can leave it off."""
        self._tol = tolerance
        self._keep = keep_captures
        self._count = 0
        self._paths: dict[tuple[str, str], tuple[int, _Fit]] = {}
        self._shots: dict[tuple[str, Shot], tuple[int, Record]] = {}

    def check(self, rec: Record) -> list[str]:
        """Every way the shot departs from what was sent, one line each."""
        i = self._count
        self._count += 1
        title = f"shot {i}" + (f" ({rec.shot.label})" if rec.shot.label else "")
        problems, fits = _judge_one(rec, self._tol)
        found = [f"{title}: {p}" for p in problems]
        for source, fit in fits.items():
            j, first = self._paths.setdefault((rec.instrument, source), (i, fit))
            if j != i:
                found += _judge_path(i, j, fit, first, source=source, tol=self._tol)
        if self._keep:
            j, earlier = self._shots.setdefault((rec.instrument, rec.shot), (i, rec))
            if j != i and (diff := _difference(earlier, rec)) > self._tol.repeat_rel:
                found.append(
                    f"shot {i} differs from shot {j}, the same shot, "
                    f"by {diff:.3g} of it"
                )
        return found


def judge(records: list[Record], tolerance: Tolerance = DEFAULT_TOLERANCE) -> list[str]:
    """Every way the records depart from what was sent, one line each."""
    judge_ = Judge(tolerance)
    return [line for rec in records for line in judge_.check(rec)]


_Window: TypeAlias = tuple[str, int, np.ndarray]


@dataclass(frozen=True)
class _Seen:
    """A pulse found in a window: where it should have come back, and at what gain."""

    where: str
    window: str
    capture: np.ndarray
    at: int
    sent: np.ndarray
    gain: complex
    # whether silence around it lets its position be found
    alone: bool


def _windows(rec: Record) -> tuple[list[_Window], list[str]]:
    """Each window's start and capture, averaged over a raw shot's iterations."""
    problems = []
    windows = []
    for w in rec.shot.windows:
        capture = rec.captures.get(w.name)
        if capture is None:
            problems.append(f"window {w.name} returned nothing")
            continue
        if rec.shot.raw:
            if len(capture) != rec.shot.iterations:
                problems.append(
                    f"window {w.name} returned {len(capture)} iterations, "
                    f"not {rec.shot.iterations}"
                )
            capture = capture.mean(axis=0)
        declared = to_samples(w.length_ns, rec.period_ns)
        if len(capture) != declared:
            problems.append(
                f"window {w.name} returned {len(capture)} samples, not {declared}"
            )
            continue
        windows.append((w.name, to_samples(w.start_ns, rec.period_ns), capture))
    return windows, problems


def _sources(shot: Shot) -> list[str]:
    return list(dict.fromkeys(p.source for p in shot.pulses))


def _from(source: str) -> str:
    return f" from {source}" if source else ""


def _expected(shot: Shot, source: str, period_ns: float, length: int) -> np.ndarray:
    signal = np.zeros(length, dtype=complex)
    for p in shot.pulses:
        if p.source != source:
            continue
        start = to_samples(p.start_ns, period_ns)
        # past the last window, a pulse is never seen
        samples = _sent(shot, p, period_ns)[: max(length - start, 0)]
        signal[start : start + len(samples)] += samples
    return signal


def _sent(shot: Shot, p: Pulse, period_ns: float) -> np.ndarray:
    phase = p.phase_deg + (shot.phase_offset_deg or 0.0)
    return p.gain * np.exp(1j * np.radians(phase)) * p.shape.samples(period_ns)


def _judge_one(rec: Record, tol: Tolerance) -> tuple[list[str], dict[str, _Fit]]:
    windows, problems = _windows(rec)
    fits: dict[str, _Fit] = {}
    if not windows:
        return problems, fits
    max_delay = to_samples(tol.delay_max_ns, rec.period_ns)
    end = max(a + len(c) for _, a, c in windows) + max_delay
    for source in _sources(rec.shot):
        expected = _expected(rec.shot, source, rec.period_ns, end)
        fit = _fit(expected, windows, max_delay)
        if fit is None:
            continue
        seen = _find_pulses(rec, source, windows, fit.delay, tol)
        if seen:
            # a pulse that came back wrong would drag a mean, and with it every other
            fit = _Fit(fit.delay, _median([s.gain for s in seen]))
        if abs(fit.gain) == 0.0:
            problems.append(f"nothing came back{_from(source)}")
            continue
        fits[source] = fit
        for s in seen:
            problems += _judge_pulse(s, fit.gain, tol)
            if rec.shot.raw:
                problems += _judge_pulse_iterations(rec, s, tol)
    if fits:
        problems += _judge_quiet(rec, windows, fits, tol)
        if rec.shot.raw:
            problems += _judge_quiet_iterations(rec, windows, fits, tol)
    return problems, fits


def _find_pulses(
    rec: Record, source: str, windows: list[_Window], delay: int, tol: Tolerance
) -> list[_Seen]:
    """The pulses long enough to measure that came back whole inside a window."""
    period = rec.period_ns
    edge = to_samples(EDGE_NS, period)
    reach = _reach(tol)
    own = [p for p in rec.shot.pulses if p.source == source]
    spans = [
        (
            to_samples(p.start_ns, period),
            to_samples(p.start_ns + p.shape.length_ns, period),
        )
        for p in own
    ]
    seen = []
    for k, p in enumerate(rec.shot.pulses):
        if p.source != source:
            continue
        sent = _sent(rec.shot, p, period)
        if len(sent) < 3 * edge:
            continue
        start = to_samples(p.start_ns, period)
        at = start + delay
        alone = not any(
            lo < start + len(sent) + reach and start - reach < hi
            for lo, hi in spans
            if (lo, hi) != (start, start + len(sent))
        )
        for name, a, c in windows:
            if a <= at and at + len(sent) <= a + len(c):
                inner = sent[edge : len(sent) - edge]
                got = c[at - a + edge : at - a + len(sent) - edge]
                gain = np.vdot(inner, got) / np.vdot(inner, inner)
                where = (
                    f"pulse {k}{_from(source)} at {p.start_ns:.0f} ns in window {name}"
                )
                seen.append(_Seen(where, name, c, at - a, sent, complex(gain), alone))
                break
    return seen


def _reach(tol: Tolerance) -> int:
    """How far a pulse's position is looked for, in samples."""
    return 4 * tol.position_samples + 8


def _median(values: list[complex]) -> complex:
    """The median magnitude, at the median phase around the values' mean direction."""
    values_ = np.asarray(values)
    # a pulse that came back as nothing has no phase to count
    some = values_[np.abs(values_) > 0]
    if not len(some):
        return 0j
    direction = np.angle(np.sum(some / np.abs(some)))
    off = np.angle(some * np.exp(-1j * direction))
    return complex(
        np.median(np.abs(values_)) * np.exp(1j * (direction + np.median(off)))
    )


def _judge_pulse(s: _Seen, path_gain: complex, tol: Tolerance) -> list[str]:
    problems = []
    ratio = s.gain / path_gain
    if abs(abs(ratio) - 1.0) > tol.gain_rel:
        problems.append(f"{s.where} came back at {abs(ratio):.3g} of the gain sent")
    if abs(np.degrees(np.angle(ratio))) > tol.phase_deg:
        problems.append(
            f"{s.where} came back turned {np.degrees(np.angle(ratio)):.1f} deg"
        )
    if not s.alone:
        return problems
    reach = _reach(tol)
    n = len(s.sent)
    shifts = range(max(-reach, -s.at), min(reach, len(s.capture) - s.at - n) + 1)
    match = [abs(np.vdot(s.sent, s.capture[s.at + d : s.at + d + n])) for d in shifts]
    shift = list(shifts)[int(np.argmax(match))]
    if abs(shift) > tol.position_samples:
        problems.append(f"{s.where} came back {shift} samples off where it was sent")
    return problems


def _iterations(off: np.ndarray) -> str:
    """Which iterations are off, by their index from 0, the first few of them."""
    index = np.flatnonzero(off)
    first = ", ".join(str(i) for i in index[:5]) + (", ..." if len(index) > 5 else "")
    return f"in {len(index)} of {len(off)} iterations ({first})"


def _judge_pulse_iterations(rec: Record, s: _Seen, tol: Tolerance) -> list[str]:
    """Each iteration of a raw shot's pulse, where the mean found it, against the
    pulse's median iteration; the mean itself is judged against what was sent."""
    edge = to_samples(EDGE_NS, rec.period_ns)
    inner = s.sent[edge : len(s.sent) - edge]
    got = rec.captures[s.window][:, s.at + edge : s.at + len(s.sent) - edge]
    gains = got @ np.conj(inner) / np.vdot(inner, inner)
    usual = _median(list(gains))
    if usual == 0:
        return []
    ratio = gains / usual
    problems = []
    off = np.abs(np.abs(ratio) - 1.0) > tol.gain_rel
    if off.any():
        worst = abs(ratio[np.argmax(np.abs(np.abs(ratio) - 1.0))])
        problems.append(
            f"{s.where} came back at as far as {worst:.3g} of its usual gain "
            f"{_iterations(off)}"
        )
    turn = np.degrees(np.angle(ratio))
    off = np.abs(turn) > tol.phase_deg
    if off.any():
        worst = turn[np.argmax(np.abs(turn))]
        problems.append(
            f"{s.where} came back turned as far as {worst:.1f} deg from its usual "
            f"phase {_iterations(off)}"
        )
    return problems


def _quiet_mask(
    rec: Record, start: int, length: int, fits: dict[str, _Fit]
) -> np.ndarray:
    """Where a window, ``start`` samples in, holds no pulse nor its edges."""
    period = rec.period_ns
    guard = to_samples(QUIET_GUARD_NS, period)
    quiet = np.ones(length, dtype=bool)
    for p in rec.shot.pulses:
        if p.source not in fits:
            continue
        at = to_samples(p.start_ns, period) + fits[p.source].delay - start
        n = to_samples(p.shape.length_ns, period)
        quiet[max(at - guard, 0) : max(min(at + n + guard, length), 0)] = False
    return quiet


def _judge_quiet(
    rec: Record, windows: list[_Window], fits: dict[str, _Fit], tol: Tolerance
) -> list[str]:
    """Between the pulses, past their edges, a window holds nothing but the noise its
    iterations average down. Full scale is what the strongest path returns of a pulse
    sent at full scale."""
    period = rec.period_ns
    full = max(abs(f.gain) for f in fits.values())
    allowed = tol.quiet_rel + tol.noise_rel / np.sqrt(rec.shot.iterations)
    problems = []
    for name, a, c in windows:
        left = np.abs(c) * _quiet_mask(rec, a, len(c), fits)
        if left.max() > allowed * full:
            at = int(np.argmax(left))
            problems.append(
                f"window {name} holds {left.max() / full:.3g} of full scale "
                f"at {at * period:.0f} ns into it, where nothing was sent"
            )
    return problems


def _judge_quiet_iterations(
    rec: Record, windows: list[_Window], fits: dict[str, _Fit], tol: Tolerance
) -> list[str]:
    """Each iteration of a raw shot holds nothing but one iteration's noise between
    the pulses."""
    full = max(abs(f.gain) for f in fits.values())
    allowed = tol.quiet_rel + tol.noise_rel
    problems = []
    for name, a, c in windows:
        quiet = _quiet_mask(rec, a, len(c), fits)
        if not quiet.any():
            continue
        peaks = np.abs(rec.captures[name][:, quiet]).max(axis=1) / full
        off = peaks > allowed
        if off.any():
            problems.append(
                f"window {name} holds as much as {peaks.max():.3g} of full scale "
                f"where nothing was sent {_iterations(off)}"
            )
    return problems


def _fit(expected: np.ndarray, windows: list[_Window], max_delay: int) -> _Fit | None:
    """The delay and gain that best map the sent signal onto every window at once."""
    padded = np.concatenate([np.zeros(max_delay, dtype=complex), expected])
    energy = np.concatenate([[0.0], np.cumsum(np.abs(padded) ** 2)])
    num = np.zeros(max_delay + 1, dtype=complex)
    den = np.zeros(max_delay + 1)
    for _, a, c in windows:
        segment = padded[a : a + max_delay + len(c)]
        size = 1 << (len(segment) + len(c)).bit_length()
        corr = np.fft.ifft(np.fft.fft(segment, size) * np.conj(np.fft.fft(c, size)))
        # the window seen d samples late reads the sent signal from a - d
        num += np.conj(corr[: max_delay + 1][::-1])
        starts = a + max_delay - np.arange(max_delay + 1)
        den += energy[starts + len(c)] - energy[starts]
    if not den.any():
        return None
    score = np.where(den > 0, np.abs(num) ** 2 / np.where(den > 0, den, 1.0), 0.0)
    delay = int(np.argmax(score))
    return _Fit(delay=delay, gain=complex(num[delay] / den[delay]))


def _judge_path(
    i: int, j: int, here: _Fit, there: _Fit, *, source: str, tol: Tolerance
) -> list[str]:
    """Shot i against shot j, which came along the same path first."""
    path = f"along the same path{_from(source)}"
    problems = []
    if abs(here.delay - there.delay) > tol.position_samples:
        problems.append(
            f"shot {i} came back {here.delay - there.delay} samples later "
            f"than shot {j} {path}"
        )
    ratio = here.gain / there.gain
    if abs(abs(ratio) - 1.0) > tol.gain_rel:
        problems.append(
            f"shot {i} came back at {abs(ratio):.3g} of the gain of shot {j} {path}"
        )
    if abs(np.degrees(np.angle(ratio))) > tol.phase_deg:
        problems.append(
            f"shot {i} came back turned {np.degrees(np.angle(ratio)):.1f} deg "
            f"from shot {j} {path}"
        )
    return problems


def _difference(a: Record, b: Record) -> float:
    names = sorted(a.captures)
    if names != sorted(b.captures) or any(
        a.captures[n].shape != b.captures[n].shape for n in names
    ):
        return float("inf")
    x = np.concatenate([a.captures[n].ravel() for n in names])
    y = np.concatenate([b.captures[n].ravel() for n in names])
    return float(np.linalg.norm(y - x) / np.linalg.norm(x))


__all__ = [
    "DEFAULT_TOLERANCE",
    "EDGE_NS",
    "QUIET_GUARD_NS",
    "Judge",
    "Record",
    "Tolerance",
    "judge",
]
