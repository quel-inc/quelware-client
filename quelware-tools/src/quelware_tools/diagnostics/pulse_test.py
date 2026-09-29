"""Per-port pulse test for a live QuEL-3 unit.

Puts the unit's monitor into loopback and, for every tx/trx port, emits a train
of rectangular pulses of swept lengths and gaps and captures all of it on the
monitor. The capture must show each pulse, and nothing else, where the train
put it: its start, taken from the first pulse's, and its length, both within a
tolerance. Pulses with no gap between them are one pulse. The check looks only
at the signal that comes out, so it holds whatever the server does to play the
train: its gaps and lengths straddle the ones where the server merges waves into
one send or splits them apart.

The monitor is restored to ``open`` before returning, even on failure.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

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
from ._delay import envelope, find_pulse_chunks

logger = logging.getLogger(__name__)

TICK_NS = 3.2
DEFAULT_LENGTHS_TICKS = (4, 8, 16, 64, 256)
DEFAULT_GAPS_TICKS = (0, 4, 28, 32, 36, 64, 256, 296, 300, 304, 1024)
_BLOCK_GAP_TICKS = 2048
_CAPTURE_MARGIN_NS = 2000.0
_AMPLITUDE = 0.8
_FS_PER_SEC = 10**15
_PROFILE_HALF_HZ = 200e6


@dataclass(frozen=True)
class Span:
    start_ns: float
    length_ns: float


@dataclass(frozen=True)
class PulseMatch:
    expected: Span
    measured: Span | None
    start_error_ns: float | None
    length_error_ns: float | None
    ok: bool


@dataclass(frozen=True)
class PortPulseResult:
    port_id: str
    passed: bool
    detail: str
    matches: tuple[PulseMatch, ...] = ()
    extras: tuple[Span, ...] = ()
    iq: np.ndarray | None = field(default=None, compare=False, repr=False)
    sample_rate_hz: float | None = None


@dataclass(frozen=True)
class PulseTestReport:
    unit_label: str
    passed: bool
    results: tuple[PortPulseResult, ...]


def plan_pulses(
    lengths_ticks: Sequence[int], gaps_ticks: Sequence[int]
) -> tuple[list[Span], list[Span]]:
    """The pulses to emit, every length followed by every gap, and the pulses the
    monitor should see, in which those with no gap between them are one."""
    emitted: list[Span] = []
    t_ticks = 0
    for length in lengths_ticks:
        for gap in gaps_ticks:
            emitted.append(Span(t_ticks * TICK_NS, length * TICK_NS))
            t_ticks += length + gap
        t_ticks += _BLOCK_GAP_TICKS
    expected: list[Span] = []
    for span in emitted:
        last = expected[-1] if expected else None
        if last is not None and np.isclose(
            last.start_ns + last.length_ns, span.start_ns
        ):
            expected[-1] = Span(last.start_ns, last.length_ns + span.length_ns)
        else:
            expected.append(span)
    return emitted, expected


def detect_pulses(
    iq: np.ndarray, sample_rate_hz: float, *, threshold_frac: float = 0.5
) -> list[Span]:
    """The pulses in a capture, each from its rising to its falling crossing of
    ``threshold_frac`` of the pulses' level, interpolated between samples."""
    env = envelope(iq)
    if env.max() <= 0:
        return []
    level = float(np.median(env[env > 0.5 * env.max()]))
    threshold = threshold_frac * level
    ns_per_sample = 1e9 / sample_rate_hz
    spans = []
    for start, end in find_pulse_chunks(env, threshold, space_thr=1, minimal_length=1):
        rise = _crossing(env, start - 1, start, threshold)
        fall = _crossing(env, end - 1, end, threshold)
        spans.append(Span(rise * ns_per_sample, (fall - rise) * ns_per_sample))
    return spans


def _crossing(env: np.ndarray, before: int, after: int, threshold: float) -> float:
    """Where ``env`` crosses ``threshold`` between two neighbouring samples."""
    if before < 0:
        return 0.0
    if after >= env.size:
        return float(env.size - 1)
    a, b = float(env[before]), float(env[after])
    if a == b:
        return float(after)
    return before + (threshold - a) / (b - a)


def compare_pulses(
    expected: Sequence[Span], measured: Sequence[Span], *, tolerance_ns: float
) -> tuple[list[PulseMatch], list[Span]]:
    """Each expected pulse matched to the measured one nearest to where it should
    start, counting from each list's first pulse; and the measured ones left over.

    A match holds if both its start and its length are within ``tolerance_ns``.
    """
    if not expected or not measured:
        return [PulseMatch(e, None, None, None, False) for e in expected], list(
            measured
        )
    e0, m0 = expected[0].start_ns, measured[0].start_ns
    unused = list(measured)
    matches = []
    for e in expected:
        rel = e.start_ns - e0
        nearest = min(unused, key=lambda m: abs(m.start_ns - m0 - rel), default=None)
        if nearest is None or abs(nearest.start_ns - m0 - rel) > 10 * tolerance_ns:
            matches.append(PulseMatch(e, None, None, None, False))
            continue
        unused.remove(nearest)
        start_err = nearest.start_ns - m0 - rel
        length_err = nearest.length_ns - e.length_ns
        ok = abs(start_err) <= tolerance_ns and abs(length_err) <= tolerance_ns
        matches.append(PulseMatch(e, nearest, start_err, length_err, ok))
    return matches, unused


async def run_pulse_test(
    client: QuelwareClient,
    unit_label: UnitLabel,
    *,
    port: str | None = None,
    tx_hz: float = 5.1e9,
    mon_hz: float = 5.0e9,
    lengths_ticks: Sequence[int] = DEFAULT_LENGTHS_TICKS,
    gaps_ticks: Sequence[int] = DEFAULT_GAPS_TICKS,
    tolerance_ns: float = 2.0,
    discard_instruments: bool = False,
) -> PulseTestReport:
    """Run the pulse test on every tx/trx port of one unit, or just ``port``.

    Preconditions are those of the tone test: an idle unit (unless
    ``discard_instruments`` is set) and an admin PAT for configuring the monitor.
    Each port's result holds its capture.
    """
    target_port = _monitor.resolve_port(unit_label, port) if port else None
    emitted, expected = plan_pulses(lengths_ticks, gaps_ticks)
    cleanup_ports: list[ResourceId] = []
    try:
        if discard_instruments:
            await _monitor.discard_unit_instruments(client, unit_label)
        await _monitor.set_monitor_loopback(client, unit_label)
        mon_port = await _monitor.monitor_port(client, unit_label)
        emit_ports = (
            [target_port]
            if target_port
            else await _monitor.emit_ports(client, unit_label)
        )
        emit_ports.sort(key=str)
        cleanup_ports = [*emit_ports, mon_port]
        logger.info(
            "testing %d port(s) with %d pulses each", len(emit_ports), len(emitted)
        )

        results: list[PortPulseResult] = []
        for emit_port in emit_ports:
            try:
                iq, sample_rate_hz = await _emit_and_capture(
                    client, emit_port, mon_port, emitted, tx_hz=tx_hz, mon_hz=mon_hz
                )
                results.append(
                    _judge(emit_port, expected, iq, sample_rate_hz, tolerance_ns)
                )
            except Exception as exc:
                logger.exception("error testing %s", emit_port)
                results.append(PortPulseResult(str(emit_port), False, f"error: {exc}"))
        passed = bool(results) and all(r.passed for r in results)
        return PulseTestReport(str(unit_label), passed, tuple(results))
    finally:
        await _monitor.restore_monitor_open(client, unit_label, cleanup_ports)


def _judge(
    emit_port: ResourceId,
    expected: Sequence[Span],
    iq: np.ndarray,
    sample_rate_hz: float,
    tolerance_ns: float,
) -> PortPulseResult:
    measured = detect_pulses(iq, sample_rate_hz)
    matches, extras = compare_pulses(expected, measured, tolerance_ns=tolerance_ns)
    bad = [m for m in matches if not m.ok]
    passed = not bad and not extras
    detail = (
        f"{len(measured)} pulses seen of {len(expected)}; "
        f"{len(bad)} off or missing, {len(extras)} unexpected"
    )
    if bad:
        worst = bad[0]
        detail += (
            f"; first off at {worst.expected.start_ns:.1f} ns "
            f"(length {worst.expected.length_ns:.1f} ns): "
            + (
                "missing"
                if worst.measured is None
                else f"start {worst.start_error_ns:+.2f} ns, "
                f"length {worst.length_error_ns:+.2f} ns"
            )
        )
    logger.info("  %s: %s (%s)", emit_port, "PASS" if passed else "FAIL", detail)
    return PortPulseResult(
        str(emit_port),
        passed,
        detail,
        tuple(matches),
        tuple(extras),
        iq=iq,
        sample_rate_hz=sample_rate_hz,
    )


async def _emit_and_capture(
    client: QuelwareClient,
    emit_port: ResourceId,
    mon_port: ResourceId,
    emitted: Sequence[Span],
    *,
    tx_hz: float,
    mon_hz: float,
) -> tuple[np.ndarray, float]:
    def _definition(alias: str, role: InstrumentRole, hz: float):
        return InstrumentDefinition(
            alias=alias,
            mode=InstrumentMode.FIXED_TIMELINE,
            role=role,
            profile=FixedTimelineProfile(hz - _PROFILE_HALF_HZ, hz + _PROFILE_HALF_HZ),
        )

    async with client.create_session([emit_port, mon_port]) as deploy_session:
        (tx_info,) = await deploy_session.deploy_instruments(
            emit_port, [_definition("pulse_test_tx", InstrumentRole.TRANSMITTER, tx_hz)]
        )
        (mon_info,) = await deploy_session.deploy_instruments(
            mon_port, [_definition("pulse_test_mon", InstrumentRole.RECEIVER, mon_hz)]
        )

    async with client.create_session([tx_info.id, mon_info.id]) as drive_session:
        tx_driver = create_instrument_driver_fixed_timeline(drive_session, tx_info)
        mon_driver = create_instrument_driver_fixed_timeline(drive_session, mon_info)
        tx_directive, mon_directive = _build_directives(tx_info, mon_info, emitted)
        await tx_driver.apply([SetFrequency(hz=tx_hz), tx_directive])
        await mon_driver.apply(
            [
                SetFrequency(hz=mon_hz),
                SetCaptureMode(mode=CaptureMode.AVERAGED_WAVEFORM),
                mon_directive,
            ]
        )
        ids = [tx_info.id, mon_info.id]
        await drive_session.trigger(ids)
        result = (await drive_session.wait_for_results(ids))[mon_info.id]

    captured = np.asarray(result.iq_waveform_result["cap"][0].iq_array)
    return captured, _FS_PER_SEC / mon_info.config.sampling_period_fs


def _build_directives(
    tx_info: InstrumentInfo, mon_info: InstrumentInfo, emitted: Sequence[Span]
):
    tx_period_ns = tx_info.config.sampling_period_fs / 1e6
    seq = Sequencer(default_sampling_period_ns=tx_period_ns)
    for inst in (tx_info, mon_info):
        seq.bind(
            inst.definition.alias,
            inst.config.sampling_period_fs,
            inst.config.timeline_step_samples,
        )
    alias = tx_info.definition.alias
    for span in emitted:
        samples = round(span.length_ns / tx_period_ns)
        name = f"pulse_{samples}"
        seq.register_waveform(name, np.full(samples, _AMPLITUDE, dtype=complex))
        seq.add_event(alias, name, start_offset_ns=span.start_ns)
    end_ns = emitted[-1].start_ns + emitted[-1].length_ns
    seq.add_capture_window(
        mon_info.definition.alias, "cap", 0.0, end_ns + _CAPTURE_MARGIN_NS
    )
    return (
        seq.export_set_fixed_timeline_directive(alias),
        seq.export_set_fixed_timeline_directive(mon_info.definition.alias),
    )


__all__ = [
    "DEFAULT_GAPS_TICKS",
    "DEFAULT_LENGTHS_TICKS",
    "PortPulseResult",
    "PulseMatch",
    "PulseTestReport",
    "Span",
    "compare_pulses",
    "detect_pulses",
    "plan_pulses",
    "run_pulse_test",
]
