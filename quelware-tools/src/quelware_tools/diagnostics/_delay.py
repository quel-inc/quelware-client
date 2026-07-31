"""Locate a pulse in a capture aligned to its emission and report its delay."""

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DelayResult:
    detected: bool
    delay_ns: float
    delay_samples: float
    rising_edge_sample: int
    peak_sample: int
    pulse_length_samples: int
    peak_magnitude: float
    noise_floor: float
    snr_db: float


def envelope(iq: np.ndarray, *, remove_dc: bool = True) -> np.ndarray:
    """Magnitude envelope; subtract the complex median first to drop LO leakage."""
    samples = np.asarray(iq)
    if samples.ndim != 1 or samples.size == 0:
        raise ValueError("iq must be a non-empty 1-D array")
    if remove_dc:
        samples = samples - np.median(samples.real) - 1j * np.median(samples.imag)
    return np.abs(samples)


def find_pulse_chunks(
    magnitude: np.ndarray,
    threshold: float,
    *,
    space_thr: int = 8,
    minimal_length: int = 4,
) -> list[tuple[int, int]]:
    """Above-threshold samples grouped into ``[start, end)`` runs, in time order.

    Runs separated by more than ``space_thr`` below-threshold samples are split;
    runs shorter than ``minimal_length`` samples are dropped as noise.
    """
    above = np.flatnonzero(magnitude > threshold)
    if above.size == 0:
        return []
    gaps = (above[1:] - above[:-1]) > space_thr
    starts = [int(above[0]), *(int(i) for i in above[1:][gaps])]
    lasts = [*(int(i) for i in above[:-1][gaps]), int(above[-1])]
    return [
        (s, e + 1)
        for s, e in zip(starts, lasts, strict=True)
        if (e + 1 - s) >= minimal_length
    ]


def measure_delay(
    iq: np.ndarray,
    sample_rate_hz: float,
    *,
    threshold_frac: float = 0.5,
    min_snr_db: float = 20.0,
    space_thr: int = 8,
    minimal_length: int = 4,
    remove_dc: bool = True,
) -> DelayResult:
    """Delay to the pulse's leading edge, as a sub-sample threshold crossing.

    The capture starts when the pulse is emitted, so the leading edge is the path
    delay. The edge is where the envelope crosses ``threshold_frac`` of the way
    from noise floor to peak; the pulse must clear ``min_snr_db`` to count.
    """
    env = envelope(iq, remove_dc=remove_dc)
    peak_sample = int(np.argmax(env))
    peak = float(env[peak_sample])
    noise_floor = float(np.median(env))
    snr_db = (
        20.0 * float(np.log10(peak / noise_floor))
        if noise_floor > 0.0
        else float("inf")
    )

    not_detected = DelayResult(
        detected=False,
        delay_ns=float("nan"),
        delay_samples=float("nan"),
        rising_edge_sample=-1,
        peak_sample=peak_sample,
        pulse_length_samples=0,
        peak_magnitude=peak,
        noise_floor=noise_floor,
        snr_db=snr_db,
    )
    if snr_db < min_snr_db:
        return not_detected

    threshold = noise_floor + threshold_frac * (peak - noise_floor)
    chunks = find_pulse_chunks(
        env, threshold, space_thr=space_thr, minimal_length=minimal_length
    )
    if not chunks:
        return not_detected

    start, end = chunks[0]
    delay_samples = _interpolate_crossing(env, start, threshold)
    return DelayResult(
        detected=True,
        delay_ns=delay_samples / sample_rate_hz * 1e9,
        delay_samples=delay_samples,
        rising_edge_sample=start,
        peak_sample=peak_sample,
        pulse_length_samples=end - start,
        peak_magnitude=peak,
        noise_floor=noise_floor,
        snr_db=snr_db,
    )


def _interpolate_crossing(env: np.ndarray, start: int, threshold: float) -> float:
    if start == 0:
        return 0.0
    prev, curr = float(env[start - 1]), float(env[start])
    if curr == prev:
        return float(start)
    return (start - 1) + (threshold - prev) / (curr - prev)


@dataclass(frozen=True)
class CombPlan:
    t_ref_ns: float
    period_ns: float
    pulse_ns: float
    arrivals_ns: tuple[float, ...]
    emit_offsets_ns: tuple[float, ...]


def comb_plan(
    delays_ns: list[float],
    *,
    round_ns: float = 1000.0,
    pulse_ns: float = 100.0,
    blank_ns: float = 100.0,
) -> CombPlan:
    """Deskew ports onto a common pulse/blank comb.

    Every port's pulse is placed on one grid so the capture reads as an evenly
    spaced ``pulse_ns``-on / ``blank_ns``-off comb: port ``i`` arrives at
    ``t_ref + i * (pulse_ns + blank_ns)``, where ``t_ref`` is ``max(delays)``
    rounded up to a ``round_ns`` boundary. Each port emits at its arrival minus
    its own delay; ``t_ref >= max(delays)`` keeps every emit offset non-negative.
    """
    if not delays_ns:
        raise ValueError("need at least one delay")
    period_ns = pulse_ns + blank_ns
    t_ref_ns = math.ceil(max(delays_ns) / round_ns) * round_ns
    arrivals_ns = tuple(t_ref_ns + i * period_ns for i in range(len(delays_ns)))
    emit_offsets_ns = tuple(a - d for a, d in zip(arrivals_ns, delays_ns, strict=True))
    return CombPlan(t_ref_ns, period_ns, pulse_ns, arrivals_ns, emit_offsets_ns)


@dataclass(frozen=True)
class CombMatch:
    expected_ns: float
    measured_ns: float | None
    deviation_samples: float | None
    ok: bool


def verify_comb(
    iq: np.ndarray,
    sample_rate_hz: float,
    expected_ns: tuple[float, ...],
    *,
    tolerance_samples: float = 2.0,
    threshold_frac: float = 0.5,
    min_snr_db: float = 15.0,
    search_radius_ns: float | None = None,
    remove_dc: bool = True,
) -> list[CombMatch]:
    """Check that each expected comb position holds a pulse within tolerance.

    Each expected arrival is checked in its own window: the local peak must clear
    ``min_snr_db`` over the noise floor, and its leading edge -- the half-height
    crossing of that local peak -- must be within ``tolerance_samples`` of the
    expected position. Keying detection to each window's own peak, not the global
    maximum, keeps a weak pulse from being lost beside a strong one. The window
    half-width defaults to a quarter of the comb spacing (a guard gap from the
    neighbouring pulse); pass ``search_radius_ns`` to set it explicitly.
    """
    env = envelope(iq, remove_dc=remove_dc)
    noise_floor = float(np.median(env))
    ns_per_sample = 1e9 / sample_rate_hz
    expected_samples = [e / ns_per_sample for e in expected_ns]

    if search_radius_ns is not None:
        radius = search_radius_ns / ns_per_sample
    elif len(expected_samples) > 1:
        pairs = zip(expected_samples[:-1], expected_samples[1:], strict=True)
        radius = 0.25 * min(b - a for a, b in pairs)
    else:
        radius = float(env.size)

    matches: list[CombMatch] = []
    for exp_s, exp_ns in zip(expected_samples, expected_ns, strict=True):
        edge = _local_leading_edge(
            env, exp_s, radius, noise_floor, threshold_frac, min_snr_db
        )
        if edge is None:
            matches.append(CombMatch(exp_ns, None, None, False))
        else:
            dev = edge - exp_s
            ok = abs(dev) <= tolerance_samples
            matches.append(CombMatch(exp_ns, edge * ns_per_sample, dev, ok))
    return matches


def _local_leading_edge(
    env: np.ndarray,
    center: float,
    radius: float,
    noise_floor: float,
    threshold_frac: float,
    min_snr_db: float,
) -> float | None:
    """Leading edge of the pulse in ``[center-radius, center+radius]``, or None.

    Returns None if the window's peak does not clear ``min_snr_db`` over the
    noise floor. Otherwise walks left from that local peak to the half-height
    crossing and interpolates it to sub-sample resolution.
    """
    lo = max(0, math.floor(center - radius))
    hi = min(env.size, math.ceil(center + radius))
    if hi <= lo:
        return None
    peak_idx = lo + int(np.argmax(env[lo:hi]))
    peak = float(env[peak_idx])
    snr_db = (
        20.0 * float(np.log10(peak / noise_floor))
        if noise_floor > 0.0
        else float("inf")
    )
    if snr_db < min_snr_db:
        return None
    threshold = noise_floor + threshold_frac * (peak - noise_floor)
    i = peak_idx
    while i > lo and float(env[i - 1]) > threshold:
        i -= 1
    return _interpolate_crossing(env, i, threshold)


__all__ = [
    "CombMatch",
    "CombPlan",
    "DelayResult",
    "comb_plan",
    "envelope",
    "find_pulse_chunks",
    "measure_delay",
    "verify_comb",
]
