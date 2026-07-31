"""Per-port path-delay measurement for a QuEL-3 unit.

Puts the unit's monitor into loopback and, one tx/trx port at a time, emits a
pulse while capturing from t=0 on the monitor, timing the pulse's arrival. The
result is the port -> monitor path delay. Requires an admin PAT and an idle
unit; the monitor is restored to ``open`` on the way out.
"""

import logging
from dataclasses import dataclass

import numpy as np
from quelware_client.core import QuelwareClient
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.unit import UnitLabel

from . import _monitor
from ._delay import comb_plan, verify_comb
from .pulse_delay import (
    PortDelayMeasurement,
    emit_comb_and_capture,
    measure_port_delay,
)

logger = logging.getLogger(__name__)

_COMB_MARGIN_NS = 200.0


@dataclass(frozen=True)
class PortDelayResult:
    port_id: str
    detected: bool
    detail: str
    measurement: PortDelayMeasurement | None = None


@dataclass(frozen=True)
class CombPulseCheck:
    port_id: str
    expected_ns: float
    measured_ns: float | None
    deviation_samples: float | None
    ok: bool


@dataclass(frozen=True)
class CombVerification:
    t_ref_ns: float
    period_ns: float
    tolerance_samples: float
    sample_rate_hz: float
    iq: np.ndarray
    checks: tuple[CombPulseCheck, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)


@dataclass(frozen=True)
class DelayTestReport:
    unit_label: str
    results: tuple[PortDelayResult, ...]
    verification: CombVerification | None = None

    @property
    def passed(self) -> bool:
        base = bool(self.results) and all(r.detected for r in self.results)
        if self.verification is not None:
            return base and self.verification.passed
        return base


async def run_delay_test(
    client: QuelwareClient,
    unit_label: UnitLabel,
    *,
    port: str | None = None,
    freq_hz: float = 5.0e9,
    pulse_length_ns: float = 100.0,
    capture_length_ns: float = 2000.0,
    iterations: int = 1,
    threshold_frac: float = 0.5,
    min_snr_db: float = 20.0,
    discard_instruments: bool = False,
    verify: bool = False,
    tolerance_samples: float = 2.0,
) -> DelayTestReport:
    """Measure the monitor path delay for every tx/trx port (or just ``port``).

    Set ``discard_instruments`` to clear any instruments already on the unit
    first, so a non-idle unit can be measured. Set ``verify`` to add a second
    pass that deskews the measured ports onto a common comb, emits them
    together, and checks each pulse lands within ``tolerance_samples``.
    """
    cleanup_ports: list[ResourceId] = []
    try:
        if discard_instruments:
            await _monitor.discard_all_instruments(client)
        await _monitor.set_monitor_loopback(client, unit_label)

        mon_port = await _monitor.monitor_port(client)
        emit_ports = [ResourceId(port)] if port else await _monitor.emit_ports(client)
        emit_ports.sort(key=str)
        cleanup_ports = [*emit_ports, mon_port]
        logger.info(
            "monitor loopback enabled; mon=%s, measuring %d emit port(s)",
            mon_port,
            len(emit_ports),
        )

        results: list[PortDelayResult] = []
        for emit_port in emit_ports:
            try:
                measurement = await measure_port_delay(
                    client,
                    emit_port,
                    mon_port,
                    freq_hz=freq_hz,
                    pulse_length_ns=pulse_length_ns,
                    capture_length_ns=capture_length_ns,
                    iterations=iterations,
                    threshold_frac=threshold_frac,
                    min_snr_db=min_snr_db,
                )
                results.append(_to_result(measurement))
            except Exception as exc:
                logger.exception("error measuring %s", emit_port)
                results.append(PortDelayResult(str(emit_port), False, f"error: {exc}"))

        verification = None
        if verify:
            verification = await _verify_comb(
                client,
                mon_port,
                results,
                freq_hz=freq_hz,
                pulse_length_ns=pulse_length_ns,
                iterations=iterations,
                threshold_frac=threshold_frac,
                tolerance_samples=tolerance_samples,
            )
        return DelayTestReport(str(unit_label), tuple(results), verification)
    finally:
        await _monitor.restore_monitor_open(client, unit_label, cleanup_ports)


async def _verify_comb(
    client: QuelwareClient,
    mon_port: ResourceId,
    results: list[PortDelayResult],
    *,
    freq_hz: float,
    pulse_length_ns: float,
    iterations: int,
    threshold_frac: float,
    tolerance_samples: float,
) -> CombVerification | None:
    port_ids: list[str] = []
    delays_ns: list[float] = []
    for r in results:
        measurement = r.measurement
        if r.detected and measurement is not None:
            port_ids.append(r.port_id)
            delays_ns.append(measurement.result.delay_ns)
    if not port_ids:
        logger.warning("no ports detected in phase 1; skipping comb verification")
        return None

    plan = comb_plan(
        delays_ns,
        round_ns=1000.0,
        pulse_ns=pulse_length_ns,
        blank_ns=pulse_length_ns,
    )
    capture_length_ns = plan.arrivals_ns[-1] + pulse_length_ns + _COMB_MARGIN_NS
    logger.info(
        "comb verify: %d ports, t_ref=%.0f ns, period=%.0f ns",
        len(port_ids),
        plan.t_ref_ns,
        plan.period_ns,
    )

    iq, sample_rate_hz = await emit_comb_and_capture(
        client,
        [ResourceId(p) for p in port_ids],
        mon_port,
        freq_hz=freq_hz,
        emit_offsets_ns=plan.emit_offsets_ns,
        pulse_length_ns=pulse_length_ns,
        capture_length_ns=capture_length_ns,
        iterations=iterations,
    )
    matches = verify_comb(
        iq,
        sample_rate_hz,
        plan.arrivals_ns,
        tolerance_samples=tolerance_samples,
        threshold_frac=threshold_frac,
        search_radius_ns=0.5 * pulse_length_ns,  # half the blank gap: guard neighbours
    )
    checks = tuple(
        CombPulseCheck(pid, m.expected_ns, m.measured_ns, m.deviation_samples, m.ok)
        for pid, m in zip(port_ids, matches, strict=True)
    )
    return CombVerification(
        plan.t_ref_ns, plan.period_ns, tolerance_samples, sample_rate_hz, iq, checks
    )


def _to_result(measurement: PortDelayMeasurement) -> PortDelayResult:
    r = measurement.result
    if r.detected:
        detail = (
            f"delay {r.delay_ns:.1f} ns ({r.delay_samples:.1f} samples), "
            f"{r.snr_db:.1f} dB, pulse {r.pulse_length_samples} samples"
        )
    else:
        detail = f"no pulse ({r.snr_db:.1f} dB over noise)"
    return PortDelayResult(measurement.emit_port, r.detected, detail, measurement)


__all__ = [
    "CombPulseCheck",
    "CombVerification",
    "DelayTestReport",
    "PortDelayResult",
    "run_delay_test",
]
