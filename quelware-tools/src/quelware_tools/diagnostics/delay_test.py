"""Per-port path-delay measurement for a QuEL-3 unit.

Puts the unit's monitor into loopback and, one tx/trx port at a time, emits a
pulse while capturing from t=0 on the monitor, timing the pulse's arrival. The
result is the port -> monitor path delay. Requires an admin PAT and an idle
unit; the monitor is restored to ``open`` on the way out.
"""

import logging
from dataclasses import dataclass

from quelware_client.core import QuelwareClient
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.unit import UnitLabel

from . import _monitor
from .pulse_delay import PortDelayMeasurement, measure_port_delay

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortDelayResult:
    port_id: str
    detected: bool
    detail: str
    measurement: PortDelayMeasurement | None = None


@dataclass(frozen=True)
class DelayTestReport:
    unit_label: str
    results: tuple[PortDelayResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(r.detected for r in self.results)


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
) -> DelayTestReport:
    """Measure the monitor path delay for every tx/trx port (or just ``port``).

    Set ``discard_instruments`` to clear any instruments already on the unit
    first, so a non-idle unit can be measured.
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
        return DelayTestReport(str(unit_label), tuple(results))
    finally:
        await _monitor.restore_monitor_open(client, unit_label, cleanup_ports)


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


__all__ = ["DelayTestReport", "PortDelayResult", "run_delay_test"]
