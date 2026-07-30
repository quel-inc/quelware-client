"""Locate a pulse in a capture aligned to its emission and report its delay."""

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


__all__ = ["DelayResult", "envelope", "find_pulse_chunks", "measure_delay"]
