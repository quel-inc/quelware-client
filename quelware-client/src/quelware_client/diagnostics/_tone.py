from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ToneResult:
    """Outcome of looking for a single expected tone in a captured IQ trace."""

    expected_hz: float
    measured_hz: float
    peak_to_median_db: float
    within_tolerance: bool
    above_threshold: bool

    @property
    def ok(self) -> bool:
        return self.within_tolerance and self.above_threshold


def detect_tone(
    iq: np.ndarray,
    sample_rate_hz: float,
    expected_hz: float,
    *,
    freq_tol_hz: float,
    min_peak_to_median_db: float,
) -> ToneResult:
    """Locate the dominant tone in a complex IQ trace and grade it.

    The trace is expected to contain a single tone (the transmitted signal seen
    through the internal loopback). The dominant FFT bin gives the measured
    frequency; the peak's height over the spectrum's median gives a crude SNR.
    The tone passes when it sits within ``freq_tol_hz`` of ``expected_hz`` and
    rises at least ``min_peak_to_median_db`` above the noise floor.

    Args:
        iq: Captured complex samples.
        sample_rate_hz: Sample rate of ``iq``.
        expected_hz: Baseband frequency the tone should appear at (the transmit
            frequency down-converted by the capturing mixer).
        freq_tol_hz: Allowed deviation of the measured tone from ``expected_hz``.
        min_peak_to_median_db: Minimum peak-to-median magnitude, in dB.
    """
    samples = np.asarray(iq)
    if samples.ndim != 1 or samples.size == 0:
        raise ValueError("iq must be a non-empty 1-D array")

    spectrum = np.abs(np.fft.fftshift(np.fft.fft(samples)))
    freqs = np.fft.fftshift(np.fft.fftfreq(samples.size, d=1.0 / sample_rate_hz))

    peak_idx = int(np.argmax(spectrum))
    measured_hz = float(freqs[peak_idx])
    peak = float(spectrum[peak_idx])
    median = float(np.median(spectrum))
    peak_to_median_db = (
        20.0 * float(np.log10(peak / median)) if median > 0.0 else float("inf")
    )

    return ToneResult(
        expected_hz=expected_hz,
        measured_hz=measured_hz,
        peak_to_median_db=peak_to_median_db,
        within_tolerance=abs(measured_hz - expected_hz) <= freq_tol_hz,
        above_threshold=peak_to_median_db >= min_peak_to_median_db,
    )


def top_peaks(
    iq: np.ndarray, sample_rate_hz: float, count: int = 5
) -> list[tuple[float, float]]:
    """Return ``(frequency_hz, db_over_median)`` for the strongest spectral bins.

    Diagnostic aid: shows where the captured energy actually sits, independent
    of any expected frequency. Adjacent bins of one tone may appear together.
    """
    samples = np.asarray(iq)
    spectrum = np.abs(np.fft.fftshift(np.fft.fft(samples)))
    freqs = np.fft.fftshift(np.fft.fftfreq(samples.size, d=1.0 / sample_rate_hz))
    median = float(np.median(spectrum))
    order = np.argsort(spectrum)[::-1][:count]
    return [
        (
            float(freqs[i]),
            20.0 * float(np.log10(spectrum[i] / median))
            if median > 0.0
            else float("inf"),
        )
        for i in order
    ]


__all__ = ["ToneResult", "detect_tone", "top_peaks"]
