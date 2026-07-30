"""Measure the delay from an emitting port to a capturing port.

Emit a short pulse and open the capture window at the same timeline instant
(t=0), then locate the pulse in the capture: its leading edge is the path delay
(analog loopback + digital pipeline). Transmit and capture share one frequency
so the pulse shows as a clean baseband envelope.

Topology-agnostic: it takes any ``(emit_port, capture_port)`` pair. Wiring the
capture port to see the emit port -- e.g. a QuEL-3 monitor in loopback -- is the
caller's job.
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

from ._delay import DelayResult, measure_delay

logger = logging.getLogger(__name__)

_EMIT_ALIAS = "pulse_delay_tx"
_CAPTURE_ALIAS = "pulse_delay_cap"
_FS_PER_SEC = 10**15
_PROFILE_HALF_HZ = 200e6


@dataclass(frozen=True)
class PortDelayMeasurement:
    emit_port: str
    capture_port: str
    result: DelayResult
    iq: np.ndarray
    sample_rate_hz: float


async def measure_port_delay(
    client: QuelwareClient,
    emit_port: ResourceId,
    capture_port: ResourceId,
    *,
    freq_hz: float = 5.0e9,
    pulse_length_ns: float = 100.0,
    capture_length_ns: float = 2000.0,
    amplitude: float = 0.5,
    iterations: int = 1,
    threshold_frac: float = 0.5,
    min_snr_db: float = 20.0,
) -> PortDelayMeasurement:
    """Emit a pulse on ``emit_port`` and time its arrival at ``capture_port``."""
    iq, sample_rate_hz = await _emit_pulse_and_capture(
        client,
        emit_port,
        capture_port,
        freq_hz=freq_hz,
        pulse_length_ns=pulse_length_ns,
        capture_length_ns=capture_length_ns,
        amplitude=amplitude,
        iterations=iterations,
    )
    result = measure_delay(
        iq, sample_rate_hz, threshold_frac=threshold_frac, min_snr_db=min_snr_db
    )
    logger.info(
        "%s -> %s: %s",
        emit_port,
        capture_port,
        f"delay {result.delay_ns:.1f} ns ({result.delay_samples:.1f} samples), "
        f"{result.snr_db:.1f} dB"
        if result.detected
        else f"no pulse ({result.snr_db:.1f} dB over noise)",
    )
    return PortDelayMeasurement(
        str(emit_port), str(capture_port), result, iq, sample_rate_hz
    )


async def _emit_pulse_and_capture(
    client: QuelwareClient,
    emit_port: ResourceId,
    capture_port: ResourceId,
    *,
    freq_hz: float,
    pulse_length_ns: float,
    capture_length_ns: float,
    amplitude: float,
    iterations: int,
) -> tuple[np.ndarray, float]:
    profile = FixedTimelineProfile(
        freq_hz - _PROFILE_HALF_HZ, freq_hz + _PROFILE_HALF_HZ
    )
    tx_def = InstrumentDefinition(
        alias=_EMIT_ALIAS,
        mode=InstrumentMode.FIXED_TIMELINE,
        role=InstrumentRole.TRANSMITTER,
        profile=profile,
    )
    cap_def = InstrumentDefinition(
        alias=_CAPTURE_ALIAS,
        mode=InstrumentMode.FIXED_TIMELINE,
        role=InstrumentRole.RECEIVER,
        profile=profile,
    )

    async with client.create_session([emit_port, capture_port]) as deploy_session:
        (tx_info,) = await deploy_session.deploy_instruments(emit_port, [tx_def])
        (cap_info,) = await deploy_session.deploy_instruments(capture_port, [cap_def])

    async with client.create_session([tx_info.id, cap_info.id]) as drive_session:
        tx_driver = create_instrument_driver_fixed_timeline(drive_session, tx_info)
        cap_driver = create_instrument_driver_fixed_timeline(drive_session, cap_info)

        tx_directive, cap_directive = _build_directives(
            tx_info,
            cap_info,
            pulse_length_ns=pulse_length_ns,
            capture_length_ns=capture_length_ns,
            amplitude=amplitude,
            iterations=iterations,
        )
        await tx_driver.apply([SetFrequency(hz=freq_hz), tx_directive])
        await cap_driver.apply(
            [
                SetFrequency(hz=freq_hz),
                SetCaptureMode(mode=CaptureMode.AVERAGED_WAVEFORM),
                cap_directive,
            ]
        )

        await drive_session.trigger([tx_info.id, cap_info.id])
        result = await cap_driver.fetch_result()

    captured = np.asarray(result.iq_waveform_result["cap"][0].iq_array)
    return captured, _FS_PER_SEC / cap_info.config.sampling_period_fs


def _build_directives(
    tx_info: InstrumentInfo,
    cap_info: InstrumentInfo,
    *,
    pulse_length_ns: float,
    capture_length_ns: float,
    amplitude: float,
    iterations: int,
):
    """Pulse at t=0 on tx and a capture window from t=0 on cap, one timeline."""
    tx_period_ns = tx_info.config.sampling_period_fs / 1_000_000
    seq = Sequencer(default_sampling_period_ns=tx_period_ns, enforce_sample_grid=False)
    for inst in (tx_info, cap_info):
        seq.bind(
            inst.definition.alias,
            inst.config.sampling_period_fs,
            inst.config.timeline_step_samples,
        )
    samples = max(1, round(pulse_length_ns / tx_period_ns))
    seq.register_waveform("pulse", np.full(samples, amplitude + 0.0j, dtype=complex))
    seq.add_event(tx_info.definition.alias, "pulse", 0.0)
    seq.add_capture_window(cap_info.definition.alias, "cap", 0.0, capture_length_ns)
    seq.set_iterations(iterations)
    return (
        seq.export_set_fixed_timeline_directive(tx_info.definition.alias),
        seq.export_set_fixed_timeline_directive(cap_info.definition.alias),
    )


__all__ = ["PortDelayMeasurement", "measure_port_delay"]
