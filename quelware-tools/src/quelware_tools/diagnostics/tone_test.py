"""Per-port tone test for a live QuEL-3 system.

Drives the public client SDK against an already-running manager + edge server
(reachable via ``client``, using an admin PAT) to confirm the internal signal
path is healthy: it puts the unit's monitor into loopback and, for every
tx/trx port, emits a long CW tone and checks that the tone appears in a monitor
capture taken from inside the CW. Capturing well inside a long emission makes
the check robust to the (unknown) loopback + digital-pipeline delay. The
monitor is always restored to ``open`` before returning, even on failure.

This targets a real (or fidelity-simulating) backend; the model-agnostic fake
worker returns no signal, so a passing fidelity result only means something
against real hardware or the device mock. It requires an idle unit (no deployed
instruments) and admin privileges, so it is a maintenance-window operation --
e.g. a health check after an on-site software update.
"""

import logging
from dataclasses import dataclass

import numpy as np
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core import QuelwareClient
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)
from quelware_core.entities.directives import (
    CaptureMode,
    SetCaptureMode,
    SetFrequency,
)
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.unit import UnitLabel

from . import _monitor
from ._tone import ToneResult, detect_tone, top_peaks

logger = logging.getLogger(__name__)

_FS_PER_SEC = 10**15
_PROFILE_HALF_HZ = 200e6


@dataclass(frozen=True)
class PortToneResult:
    port_id: str
    passed: bool
    detail: str
    tone: ToneResult | None = None


@dataclass(frozen=True)
class ToneTestReport:
    unit_label: str
    passed: bool
    results: tuple[PortToneResult, ...]


async def run_tone_test(
    client: QuelwareClient,
    unit_label: UnitLabel,
    *,
    port: str | None = None,
    tx_hz: float = 5.1e9,
    mon_hz: float = 5.0e9,
    min_peak_to_median_db: float = 20.0,
    cw_length_ns: float = 4000.0,
    capture_start_ns: float = 1000.0,
    capture_length_ns: float = 800.0,
    iterations: int = 1,
) -> ToneTestReport:
    """Run the per-port tone test on one unit.

    Tests every tx/trx port by default, or just ``port`` when given. For each,
    emits a ``cw_length_ns`` CW and captures ``capture_length_ns`` starting at
    ``capture_start_ns`` (a margin past the path delay) from inside that CW.

    Preconditions: the unit is idle (no instruments) and ``client`` was built
    with an admin PAT (configuring the monitor needs the CONFIGURE_UNIT
    capability). The monitor is restored to ``open`` before returning, even on
    failure.
    """
    cleanup_ports: list[ResourceId] = []
    try:
        await _monitor.set_monitor_loopback(client, unit_label)

        mon_port = await _monitor.monitor_port(client)
        emit_ports = [ResourceId(port)] if port else await _monitor.emit_ports(client)
        emit_ports.sort(key=str)
        cleanup_ports = [*emit_ports, mon_port]
        logger.info(
            "monitor loopback enabled; mon=%s, testing %d emit port(s)",
            mon_port,
            len(emit_ports),
        )

        expected_hz = tx_hz - mon_hz
        freq_tol_hz = 1e9 / capture_length_ns  # one FFT bin (1 / capture length)

        results: list[PortToneResult] = []
        for emit_port in emit_ports:
            try:
                results.append(
                    await _check_port(
                        client,
                        emit_port,
                        mon_port,
                        tx_freq_hz=tx_hz,
                        mon_freq_hz=mon_hz,
                        expected_hz=expected_hz,
                        freq_tol_hz=freq_tol_hz,
                        min_peak_to_median_db=min_peak_to_median_db,
                        cw_length_ns=cw_length_ns,
                        capture_start_ns=capture_start_ns,
                        capture_length_ns=capture_length_ns,
                        iterations=iterations,
                    )
                )
            except Exception as exc:
                logger.exception("error testing %s", emit_port)
                results.append(PortToneResult(str(emit_port), False, f"error: {exc}"))
        passed = bool(results) and all(r.passed for r in results)
        return ToneTestReport(str(unit_label), passed, tuple(results))
    finally:
        await _monitor.restore_monitor_open(client, unit_label, cleanup_ports)


async def _check_port(
    client: QuelwareClient,
    emit_port: ResourceId,
    mon_port: ResourceId,
    *,
    tx_freq_hz: float,
    mon_freq_hz: float,
    expected_hz: float,
    freq_tol_hz: float,
    min_peak_to_median_db: float,
    cw_length_ns: float,
    capture_start_ns: float,
    capture_length_ns: float,
    iterations: int,
) -> PortToneResult:
    logger.info(
        "testing %s -> monitor (tx=%.6g Hz, expected baseband=%.6g Hz)",
        emit_port,
        tx_freq_hz,
        expected_hz,
    )
    captured, sample_rate_hz = await _emit_and_capture(
        client,
        emit_port,
        mon_port,
        tx_freq_hz=tx_freq_hz,
        mon_freq_hz=mon_freq_hz,
        cw_length_ns=cw_length_ns,
        capture_start_ns=capture_start_ns,
        capture_length_ns=capture_length_ns,
        iterations=iterations,
    )
    if abs(expected_hz) > sample_rate_hz / 2:
        logger.warning(
            "  %s baseband %.4g Hz beyond Nyquist %.4g Hz (Fs=%.4g); tx/mon too far",
            emit_port,
            expected_hz,
            sample_rate_hz / 2,
            sample_rate_hz,
        )
    logger.info(
        "  %s capture: Fs=%.4g Hz, N=%d, top peaks=%s",
        emit_port,
        sample_rate_hz,
        captured.size,
        [
            (f"{f / 1e6:.1f} MHz", f"{db:.1f} dB")
            for f, db in top_peaks(captured, sample_rate_hz)
        ],
    )
    tone = detect_tone(
        captured,
        sample_rate_hz,
        expected_hz=expected_hz,
        freq_tol_hz=freq_tol_hz,
        min_peak_to_median_db=min_peak_to_median_db,
    )
    detail = (
        f"tone at {tone.measured_hz:.3e} Hz (expected {tone.expected_hz:.3e}); "
        f"{tone.peak_to_median_db:.1f} dB over noise"
    )
    logger.info("  %s: %s (%s)", emit_port, "PASS" if tone.ok else "FAIL", detail)
    return PortToneResult(str(emit_port), tone.ok, detail, tone)


async def _emit_and_capture(
    client: QuelwareClient,
    emit_port: ResourceId,
    mon_port: ResourceId,
    *,
    tx_freq_hz: float,
    mon_freq_hz: float,
    cw_length_ns: float,
    capture_start_ns: float,
    capture_length_ns: float,
    iterations: int,
) -> tuple[np.ndarray, float]:
    tx_def = InstrumentDefinition(
        alias="tone_test_tx",
        mode=InstrumentMode.FIXED_TIMELINE,
        role=InstrumentRole.TRANSMITTER,
        profile=FixedTimelineProfile(
            tx_freq_hz - _PROFILE_HALF_HZ, tx_freq_hz + _PROFILE_HALF_HZ
        ),
    )
    mon_def = InstrumentDefinition(
        alias="tone_test_mon",
        mode=InstrumentMode.FIXED_TIMELINE,
        role=InstrumentRole.RECEIVER,
        profile=FixedTimelineProfile(
            mon_freq_hz - _PROFILE_HALF_HZ, mon_freq_hz + _PROFILE_HALF_HZ
        ),
    )

    async with client.create_session([emit_port, mon_port]) as deploy_session:
        (tx_info,) = await deploy_session.deploy_instruments(emit_port, [tx_def])
        (mon_info,) = await deploy_session.deploy_instruments(mon_port, [mon_def])

    async with client.create_session([tx_info.id, mon_info.id]) as drive_session:
        tx_driver = create_instrument_driver_fixed_timeline(drive_session, tx_info)
        mon_driver = create_instrument_driver_fixed_timeline(drive_session, mon_info)

        tx_directive, mon_directive = _build_directives(
            tx_info,
            mon_info,
            cw_length_ns=cw_length_ns,
            capture_start_ns=capture_start_ns,
            capture_length_ns=capture_length_ns,
            iterations=iterations,
        )
        await tx_driver.apply(SetFrequency(hz=tx_freq_hz))
        await tx_driver.apply(tx_directive)

        await mon_driver.apply(
            [
                SetFrequency(hz=mon_freq_hz),
                SetCaptureMode(mode=CaptureMode.AVERAGED_WAVEFORM),
            ]
        )
        await mon_driver.apply(mon_directive)

        await drive_session.trigger([tx_info.id, mon_info.id])
        result = await mon_driver.fetch_result()

    captured = np.asarray(result.iq_waveform_result["cap"][0].iq_array)
    return captured, _FS_PER_SEC / mon_info.config.sampling_period_fs


def _build_directives(
    tx_info: InstrumentInfo,
    mon_info: InstrumentInfo,
    *,
    cw_length_ns: float,
    capture_start_ns: float,
    capture_length_ns: float,
    iterations: int,
):
    """Emit and capture share one timeline, so bind both to a single sequencer.

    The tx CW sets the shared length; the mon capture window lands inside it.
    """
    tx_period_ns = tx_info.config.sampling_period_fs / 1_000_000
    seq = Sequencer(default_sampling_period_ns=tx_period_ns, enforce_sample_grid=False)
    for inst in (tx_info, mon_info):
        seq.bind(
            inst.definition.alias,
            inst.config.sampling_period_fs,
            inst.config.timeline_step_samples,
        )
    samples = max(1, round(cw_length_ns / tx_period_ns))
    seq.register_waveform("cw", np.full(samples, 0.5 + 0.0j, dtype=complex))
    seq.add_event(tx_info.definition.alias, "cw", 0.0)
    seq.add_capture_window(
        mon_info.definition.alias, "cap", capture_start_ns, capture_length_ns
    )
    seq.set_iterations(iterations)
    return (
        seq.export_set_fixed_timeline_directive(tx_info.definition.alias),
        seq.export_set_fixed_timeline_directive(mon_info.definition.alias),
    )


__all__ = [
    "PortToneResult",
    "ToneTestReport",
    "run_tone_test",
]
