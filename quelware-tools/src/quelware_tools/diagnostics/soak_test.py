"""Soak test for live QuEL-3 units, all of them run at once.

Deploys a transmitter on every tx port and a transceiver on every trx port of
every unit, and then runs over and over a random train of waves on every port at
once, with a random train of capture windows on every trx port, waiting for every
instrument with ``Session.wait_for_results``; what is captured is not looked at.
Each run's wave and window lengths, gaps and iterations are drawn without regard
to the server's limits, so a run may be refused before it starts: a refusal
counts as a pass. Only the iteration blank is kept long enough for any wrap, and
the windows a port captures over all iterations within
``SoakProfile.max_total_capture_ns``, so as not to fill its capture pool. A run
that starts and then fails, times out, or breaks in any other way is a failure.

Every wave of the one port shown in a run starts with a marker, ``MARKER_TICKS``
long at full gain, and is ``HIDDEN_AMPLITUDE`` after it; the waves of every other
port are ``HIDDEN_AMPLITUDE`` throughout. A monitor in loopback would then see a
spike per wave of the shown port.

Every run draws from ``numpy.random.default_rng([seed, run])``, so a failed run
is replayed by starting from it with the same seed. The instruments deployed are
discarded before returning.
"""

import asyncio
import contextlib
import json
import logging
import math
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from grpclib import GRPCError
from grpclib.const import Status
from grpclib.exceptions import StreamTerminatedError
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core import QuelwareClient, Session
from quelware_client.core.exceptions import RunFailedError
from quelware_client.core.instrument_driver import (
    FixedTimelineInstrumentDriver,
    create_instrument_driver_fixed_timeline,
)
from quelware_core.entities.directives import (
    CaptureMode,
    SetCaptureMode,
    SetFixedTimeline,
    SetFrequency,
)
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import (
    ResourceCategory,
    ResourceId,
    extract_unit_label,
)
from quelware_core.entities.unit import UnitLabel

from . import _monitor

logger = logging.getLogger(__name__)

# one tick of the wave subsystem clock, a whole number of samples on every port
TICK_NS = 3.2
MARKER_TICKS = 4
HIDDEN_AMPLITUDE = 0.001
_PROFILE_HALF_HZ = 200e6
_WAIT_MARGIN_SEC = 10.0
_SESSION_TTL_MS = 20_000
_LEASE_EXTEND_SEC = 5.0
_CONCURRENT_DISCARDS = 32


@dataclass(frozen=True)
class SoakProfile:
    """What a run is drawn from; lengths are in ticks, multiples of 4."""

    # every port's waves and windows lie within this, 10 us
    span_ticks: int = 3124
    wave_ticks: tuple[int, ...] = (4, 8, 24, 56, 140, 340, 820, 2000)
    # each port draws one of these as the longest gap of its train, so that
    # some ports are packed and others sparse
    max_gap_ticks: tuple[int, ...] = (4, 16, 64, 256, 1024)
    zero_gap_probability: float = 0.1
    min_gain: float = 0.1
    max_gain: float = 0.9
    iterations: tuple[int, ...] = (1, 100, 1000, 10000)
    # no shorter than the 300-tick (960 ns) send interval, so no wrap is refused
    iteration_blank_ns: tuple[float, ...] = (1000.0, 2000.0, 20_000.0, 200_000.0)
    max_window_ticks: int = 2000
    # a port's windows summed over the iterations, well within its capture pool
    max_total_capture_ns: float = 10e6


DEFAULT_PROFILE = SoakProfile()


@dataclass(frozen=True)
class Wave:
    start_ns: float
    length_ns: float
    gain: float
    phase_deg: float


@dataclass(frozen=True)
class Window:
    start_ns: float
    length_ns: float


@dataclass(frozen=True)
class RunPlan:
    run: int
    length_ns: float
    iterations: int
    iteration_blank_ns: float
    shown_port: str
    waves: dict[str, tuple[Wave, ...]]
    windows: dict[str, tuple[Window, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class RunFailure:
    run: int
    # "refused" before it started; "run" when an instrument failed; "timeout";
    # "unavailable" when a unit could not be reached, the run aborted everywhere;
    # "connection" when the call was lost on the way; "error" for anything else
    kind: str
    detail: str


@dataclass
class SoakReport:
    unit_labels: list[str]
    runs: int = 0
    completed: int = 0
    refused: Counter[str] = field(default_factory=Counter)
    failures: list[RunFailure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _draw_ticks(rng: np.random.Generator, high: int) -> int:
    """A length in ticks, log-uniform up to ``high``, rounded to 4 ticks."""
    ticks = math.exp(rng.uniform(0.0, math.log(high)))
    return max(4, int(round(ticks / 4)) * 4)


def _fill_span(
    rng: np.random.Generator, draw_length: Callable[[], int], profile: SoakProfile
) -> list[tuple[int, int]]:
    """(start, length) ticks laid one after another with random gaps, until the
    next one drawn would run past the span."""
    max_gap = int(rng.choice(profile.max_gap_ticks))
    t_ticks = 0 if rng.random() < 0.5 else _draw_ticks(rng, max_gap)
    spans = []
    while t_ticks + (length_ticks := draw_length()) <= profile.span_ticks:
        spans.append((t_ticks, length_ticks))
        gap_ticks = (
            0
            if rng.random() < profile.zero_gap_probability
            else _draw_ticks(rng, max_gap)
        )
        t_ticks += length_ticks + gap_ticks
    return spans


def draw_plan(
    rng: np.random.Generator,
    run: int,
    port_ids: Sequence[str],
    profile: SoakProfile = DEFAULT_PROFILE,
    capture_port_ids: Sequence[str] = (),
) -> RunPlan:
    """Draw one run: a train of waves for every port and a train of capture
    windows for every capture port, each as dense as its port draws, and how the
    run repeats."""
    waves: dict[str, tuple[Wave, ...]] = {}
    for port in port_ids:
        spans = _fill_span(rng, lambda: int(rng.choice(profile.wave_ticks)), profile)
        waves[port] = tuple(
            Wave(
                start_ns=start * TICK_NS,
                length_ns=length * TICK_NS,
                gain=float(rng.uniform(profile.min_gain, profile.max_gain)),
                phase_deg=float(rng.uniform(0.0, 360.0)),
            )
            for start, length in spans
        )
    windows: dict[str, tuple[Window, ...]] = {}
    for port in capture_port_ids:
        spans = _fill_span(
            rng, lambda: _draw_ticks(rng, profile.max_window_ticks), profile
        )
        windows[port] = tuple(
            Window(start_ns=start * TICK_NS, length_ns=length * TICK_NS)
            for start, length in spans
        )

    length_ns = profile.span_ticks * TICK_NS
    iteration_blank_ns = float(rng.choice(profile.iteration_blank_ns))
    iterations = int(rng.choice(profile.iterations))
    for port, train in windows.items():
        kept: list[Window] = []
        for window in train:
            total_ns = sum(w.length_ns for w in kept) + window.length_ns
            if iterations * total_ns > profile.max_total_capture_ns:
                break
            kept.append(window)
        windows[port] = tuple(kept)
    return RunPlan(
        run=run,
        length_ns=length_ns,
        iterations=iterations,
        iteration_blank_ns=iteration_blank_ns,
        shown_port=str(rng.choice(list(port_ids))),
        waves=waves,
        windows=windows,
    )


def _wave_samples(length_samples: int, marker_samples: int, shown: bool) -> np.ndarray:
    samples = np.full(length_samples, HIDDEN_AMPLITUDE, dtype=complex)
    if shown:
        samples[:marker_samples] = 1.0
    return samples


def build_directives(
    plan: RunPlan,
    emit_infos: dict[str, InstrumentInfo],
) -> dict[str, SetFixedTimeline]:
    """One timeline per instrument alias, all sharing the run's length."""
    first = next(iter(emit_infos.values()))
    seq = Sequencer(
        default_sampling_period_ns=first.config.sampling_period_fs / 1e6,
        iter_blank_ns=plan.iteration_blank_ns,
    )
    seq.extend_length_ns(plan.length_ns)
    for info in emit_infos.values():
        seq.bind(
            info.definition.alias,
            info.config.sampling_period_fs,
            info.config.timeline_step_samples,
        )
    for port, train in plan.waves.items():
        info = emit_infos[port]
        alias = info.definition.alias
        period_ns = info.config.sampling_period_fs / 1e6
        marker_samples = round(MARKER_TICKS * TICK_NS / period_ns)
        for wave in train:
            length_samples = round(wave.length_ns / period_ns)
            name = f"{alias}_{length_samples}"
            seq.register_waveform(
                name,
                _wave_samples(length_samples, marker_samples, port == plan.shown_port),
                sampling_period_ns=period_ns,
            )
            seq.add_event(
                alias,
                name,
                start_offset_ns=wave.start_ns,
                gain=wave.gain,
                phase_offset_deg=wave.phase_deg,
            )
    for port, train in plan.windows.items():
        alias = emit_infos[port].definition.alias
        for index, window in enumerate(train):
            seq.add_capture_window(
                alias, f"cap{index}", window.start_ns, window.length_ns
            )
    seq.set_iterations(plan.iterations)
    return {
        info.definition.alias: seq.export_set_fixed_timeline_directive(
            info.definition.alias
        )
        for info in emit_infos.values()
    }


def _is_capture_port(port: ResourceId | str) -> bool:
    return _monitor.port_name(ResourceId(str(port))).startswith("trx")


@contextlib.asynccontextmanager
async def _leased_session(
    client: QuelwareClient, resource_ids: Sequence[ResourceId]
) -> AsyncIterator[tuple[Session, asyncio.Task[None]]]:
    """A session whose lease is kept by the task yielded with it; the task ends,
    raising, only if an extension fails."""
    async with client.create_session(
        list(resource_ids), ttl_ms=_SESSION_TTL_MS
    ) as session:
        lease = asyncio.create_task(_keep_lease(session))
        try:
            yield session, lease
        finally:
            lease.cancel()


async def _per_unit(
    resource_ids: Sequence[ResourceId],
    work: Callable[[ResourceId], Awaitable[object]],
) -> None:
    """``work`` on every resource, one after another within a unit and the units
    in parallel."""
    by_unit: dict[UnitLabel, list[ResourceId]] = {}
    for rid in resource_ids:
        by_unit.setdefault(extract_unit_label(rid), []).append(rid)

    async def _on_unit(rids: list[ResourceId]) -> None:
        for rid in rids:
            await work(rid)

    await asyncio.gather(*(_on_unit(rids) for rids in by_unit.values()))


async def _deploy(
    client: QuelwareClient, emit_ports: Sequence[ResourceId], tx_hz: float
) -> dict[str, InstrumentInfo]:
    deployed: dict[str, InstrumentInfo] = {}
    async with _leased_session(client, emit_ports) as (session, _):

        async def _deploy_one(port: ResourceId) -> None:
            definition = InstrumentDefinition(
                alias=f"soak_{_monitor.port_name(port)}",
                mode=InstrumentMode.FIXED_TIMELINE,
                role=(
                    InstrumentRole.TRANSCEIVER
                    if _is_capture_port(port)
                    else InstrumentRole.TRANSMITTER
                ),
                profile=FixedTimelineProfile(
                    tx_hz - _PROFILE_HALF_HZ, tx_hz + _PROFILE_HALF_HZ
                ),
            )
            (info,) = await session.deploy_instruments(port, [definition])
            deployed[str(port)] = info

        await _per_unit(emit_ports, _deploy_one)
    return {str(port): deployed[str(port)] for port in emit_ports}


async def _discard(client: QuelwareClient, ports: Sequence[ResourceId]) -> None:
    calls = asyncio.Semaphore(_CONCURRENT_DISCARDS)

    async def _discard_one(port: ResourceId) -> None:
        async with calls:
            await session.discard_instruments(port)

    async with _leased_session(client, ports) as (session, _):
        await asyncio.gather(*(_discard_one(p) for p in ports))


async def _judge_run(
    session: Session,
    drivers: dict[str, FixedTimelineInstrumentDriver],
    unit_aliases: dict[UnitLabel, list[str]],
    ids: list[ResourceId],
    plan: RunPlan,
    directives: dict[str, SetFixedTimeline],
    initialize: bool = False,
) -> RunFailure | None:
    """Run one plan on every unit at once, configuring the units in parallel;
    None when it completed, a refusal or a failure otherwise. With
    ``initialize``, the instruments are initialized first."""
    period_ns = plan.length_ns + plan.iteration_blank_ns
    timeout_sec = plan.iterations * period_ns * 1e-9 + _WAIT_MARGIN_SEC
    laps: dict[str, float] = {}
    lap_start = time.monotonic()

    def _lap(step: str) -> None:
        nonlocal lap_start
        now = time.monotonic()
        laps[step] = now - lap_start
        lap_start = now

    async def _configure_unit(aliases: list[str]) -> None:
        for alias in aliases:
            await drivers[alias].apply(directives[alias])

    try:
        if initialize:
            await session.initialize(ids)
            _lap("initialize")
        await asyncio.gather(*(_configure_unit(a) for a in unit_aliases.values()))
        _lap("configure")
        await session.trigger(ids)
        _lap("trigger")
        await session.wait_for_results(ids, timeout_sec=timeout_sec)
        _lap("wait")
    except Exception as e:
        return RunFailure(plan.run, *_classify(e))
    finally:
        logger.info(
            "run %d took %s (%d waves, iterations %d)",
            plan.run,
            ", ".join(f"{step} {sec:.3f} s" for step, sec in laps.items()),
            sum(len(t) for t in plan.waves.values()),
            plan.iterations,
        )
    return None


def _classify(e: Exception) -> tuple[str, str]:
    """The kind of a run's failure, as ``RunFailure.kind`` lists them, and its
    detail."""
    kind, detail = "error", f"{type(e).__name__}: {e}"
    if isinstance(e, GRPCError):
        if e.status is Status.INVALID_ARGUMENT:
            kind, detail = "refused", _refusal_reason(e.message or "")
        elif e.status is Status.UNAVAILABLE:
            kind, detail = "unavailable", e.message or ""
        else:
            detail = f"{e.status.name}: {e.message}"
    elif isinstance(e, RunFailedError):
        kind, detail = "run", str(e)
    elif isinstance(e, TimeoutError):
        kind, detail = "timeout", str(e)
    elif isinstance(e, StreamTerminatedError):
        kind, detail = "connection", str(e)
    return kind, detail


def _refusal_reason(message: str) -> str:
    """The kind of refusal, without the numbers that differ from run to run."""
    words = [w for w in message.split() if not any(c.isdigit() for c in w)]
    return " ".join(words)[:80]


def _save_failure(save_dir: Path, plan: RunPlan, failure: RunFailure) -> None:
    save_dir.mkdir(parents=True, exist_ok=True)
    path = save_dir / f"run{plan.run:06d}.json"
    path.write_text(json.dumps({"failure": asdict(failure), "plan": asdict(plan)}))


async def _keep_lease(session: Session) -> None:
    """Extend the session's lease for as long as it runs; returns only by raising."""
    while True:
        await asyncio.sleep(_LEASE_EXTEND_SEC)
        await session.extend(_SESSION_TTL_MS)


async def _find_units(client: QuelwareClient) -> list[UnitLabel]:
    rinfos = await client.list_resource_infos()
    return sorted(
        {
            extract_unit_label(r.id)
            for r in rinfos
            if r.category is ResourceCategory.PORT
        },
        key=str,
    )


async def run_soak_test(  # noqa: PLR0913
    client: QuelwareClient,
    unit_labels: Sequence[UnitLabel] | None = None,
    *,
    runs: int | None = None,
    duration_sec: float | None = None,
    seed: int = 0,
    start_run: int = 0,
    profile: SoakProfile = DEFAULT_PROFILE,
    tx_hz: float = 5.1e9,
    save_dir: Path | None = None,
    stop_on_failure: bool = False,
    report_every: int = 100,
    discard_instruments: bool = False,
    initialize_each_run: bool = False,
) -> SoakReport:
    """Run the soak test on the units until ``runs`` or ``duration_sec`` is spent.

    Every run goes on all the units at once, under one session and one trigger;
    ``unit_labels`` of None takes every unit the manager knows. With neither
    ``runs`` nor ``duration_sec`` it runs until interrupted. The units' tx/trx
    ports must be idle, unless ``discard_instruments`` is set. With
    ``initialize_each_run``, every run initializes the instruments before it
    configures them, as a client that starts each run afresh does.
    """
    units = list(unit_labels) if unit_labels else await _find_units(client)
    report = SoakReport([str(u) for u in units])
    emit_ports: list[ResourceId] = []
    started_at = time.monotonic()
    try:
        if discard_instruments:
            ports = [p for unit in units for p in await _monitor.port_ids(client, unit)]
            logger.info(
                "discarding the instruments on %d ports of %d units",
                len(ports),
                len(units),
            )
            await _discard(client, ports)
        for unit in units:
            emit_ports += sorted(await _monitor.emit_ports(client, unit), key=str)
        emit_infos = await _deploy(client, emit_ports, tx_hz)
        capture_ports = [p for p in emit_infos if _is_capture_port(p)]
        logger.info(
            "soak test on %d units, %d emit ports, %d of them capturing",
            len(units),
            len(emit_ports),
            len(capture_ports),
        )

        ids = [info.id for info in emit_infos.values()]
        unit_aliases: dict[UnitLabel, list[str]] = {}
        for info in emit_infos.values():
            unit_aliases.setdefault(extract_unit_label(info.id), []).append(
                info.definition.alias
            )
        async with _leased_session(client, ids) as (session, lease):
            drivers = {
                info.definition.alias: create_instrument_driver_fixed_timeline(
                    session, info
                )
                for info in emit_infos.values()
            }

            async def _set_up(port: ResourceId) -> None:
                directives = [SetFrequency(hz=tx_hz)]
                if str(port) in capture_ports:
                    directives.append(
                        SetCaptureMode(mode=CaptureMode.AVERAGED_WAVEFORM)
                    )
                await drivers[emit_infos[str(port)].definition.alias].apply(directives)

            await _per_unit(emit_ports, _set_up)

            run = start_run
            while (runs is None or report.runs < runs) and (
                duration_sec is None or time.monotonic() - started_at < duration_sec
            ):
                if lease.done():
                    exc = lease.exception()
                    failure = RunFailure(run, "lease", f"{type(exc).__name__}: {exc}")
                    report.failures.append(failure)
                    logger.error("lease lost before run %d: %s", run, failure.detail)
                    break
                plan = draw_plan(
                    np.random.default_rng([seed, run]),
                    run,
                    list(emit_infos),
                    profile,
                    capture_ports,
                )
                directives = build_directives(plan, emit_infos)
                failure = await _judge_run(
                    session,
                    drivers,
                    unit_aliases,
                    ids,
                    plan,
                    directives,
                    initialize=initialize_each_run,
                )
                report.runs += 1
                if failure is None:
                    report.completed += 1
                elif failure.kind == "refused":
                    report.refused[failure.detail] += 1
                else:
                    report.failures.append(failure)
                    logger.error("run %d %s: %s", run, failure.kind, failure.detail)
                    if save_dir is not None:
                        _save_failure(save_dir, plan, failure)
                    if stop_on_failure:
                        break
                if report.runs % report_every == 0:
                    logger.info(
                        "%d runs: %d completed, %d refused, %d failed",
                        report.runs,
                        report.completed,
                        sum(report.refused.values()),
                        len(report.failures),
                    )
                run += 1
        return report
    finally:
        if emit_ports:
            try:
                await _discard(client, emit_ports)
            except Exception:
                logger.exception("could not discard the soak test's instruments")


__all__ = [
    "HIDDEN_AMPLITUDE",
    "MARKER_TICKS",
    "TICK_NS",
    "RunFailure",
    "RunPlan",
    "SoakProfile",
    "SoakReport",
    "Wave",
    "Window",
    "build_directives",
    "draw_plan",
    "run_soak_test",
]
