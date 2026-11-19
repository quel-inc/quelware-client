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

With ``check_monitor``, the units are put in monitor loopback and the windows are
captured on each unit's monitor rather than on its trx ports. One port of each unit
is shown in a run, at full scale throughout its waves, and every other port sends
waves of nothing, so that its monitor receives that port's waves alone; what it
captures is judged against them (``correctness.Judge``), and a run that comes back
otherwise than it was sent is a failure.

Every run draws from ``numpy.random.default_rng([seed, run])``, so a failed run
is replayed by starting from it with the same seed. The instruments deployed are
discarded before returning.
"""

import asyncio
import contextlib
import dataclasses
import importlib.metadata
import json
import logging
import math
import time
from collections import Counter
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterator,
    Mapping,
    Sequence,
)
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
    FixedTimelineDirective,
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
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.unit import UnitLabel

from . import _monitor, correctness, shots

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
# the version of the timings file's layout, raised when a reader would misread it
TIMINGS_FORMAT = 1


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
    # the share of runs that return every iteration rather than their mean, and
    # the iterations they repeat, few enough to leave their windows some length
    raw_share: float = 0.25
    raw_iterations: tuple[int, ...] = (1, 10, 100)
    # a raw run's windows summed over the iterations; returning much more holds up
    # the unit's other calls while it is sent
    max_raw_capture_ns: float = 40_000.0
    # a run of several jobs, as a client packs points or sequences into one trigger:
    # each job's waves over the span, then its readout window when ``readout_ticks``
    # is set (instead of drawn windows), then the blank before the next job; the
    # readouts beyond the capture budget are left out, and without ``readout_ticks``
    # the windows are drawn over the first job only
    jobs: int = 1
    job_blank_ticks: int = 0
    readout_ticks: int = 0


DEFAULT_PROFILE = SoakProfile()

# 30 randomized benchmarking sequences of about 2000 gates packed into one trigger,
# a shot interval apart, each ending in a readout as far as the capture budget goes
# (22 of them at 1024 iterations): a small waveform library but tens of thousands of
# events per port.
PACKED_RB_PROFILE = SoakProfile(
    span_ticks=16400,
    wave_ticks=(4, 8),
    max_gap_ticks=(4,),
    zero_gap_probability=0.5,
    iterations=(1024,),
    iteration_blank_ns=(153_600.0,),
    raw_share=0.0,
    max_total_capture_ns=12e6,
    jobs=30,
    job_blank_ticks=48000,
    readout_ticks=160,
)

# 50 points of a calibration sweep packed into one trigger, a shot interval apart:
# each a few short pulses and a readout, as far as the capture budget goes.
PACKED_SWEEP_PROFILE = SoakProfile(
    span_ticks=60,
    wave_ticks=(4, 8, 20),
    max_gap_ticks=(4, 16),
    iterations=(1024,),
    iteration_blank_ns=(153_600.0,),
    raw_share=0.0,
    max_total_capture_ns=12e6,
    jobs=50,
    job_blank_ticks=48000,
    readout_ticks=160,
)

# Capture windows up to 8.3 us long repeated with a short blank, as a resonator or
# qubit spectroscopy point, which is sent alone.
SPECTROSCOPY_PROFILE = SoakProfile(
    span_ticks=2600,
    wave_ticks=(320,),
    max_gap_ticks=(1024,),
    iterations=(1024,),
    iteration_blank_ns=(1024.0,),
    max_window_ticks=2600,
    raw_share=0.0,
)

# Flat pulses of 1 and 4 us sampled whole, as a cross-resonance tomography point,
# which is sent alone.
DENSE_CR_PROFILE = SoakProfile(
    span_ticks=2600,
    wave_ticks=(312, 1248),
    max_gap_ticks=(4,),
    zero_gap_probability=0.5,
    iterations=(2048,),
    iteration_blank_ns=(153_600.0,),
    max_window_ticks=200,
    raw_share=0.0,
)


@dataclass(frozen=True)
class RoundEntry:
    """A kind of run, and how many runs of it a round holds."""

    kind: str
    profile: SoakProfile
    runs: int


# A round of the default kinds: the light ones many times, the heavy ones a few times
# at their heaviest, randomized benchmarking at its two longest lengths.
DEFAULT_ROUND: tuple[RoundEntry, ...] = (
    RoundEntry("sparse", DEFAULT_PROFILE, 20),
    RoundEntry("spectroscopy", SPECTROSCOPY_PROFILE, 20),
    RoundEntry("dense-cr", DENSE_CR_PROFILE, 20),
    RoundEntry("packed-sweep", PACKED_SWEEP_PROFILE, 4),
    RoundEntry(
        "packed-rb-1024", dataclasses.replace(PACKED_RB_PROFILE, span_ticks=8200), 2
    ),
    RoundEntry("packed-rb-2048", PACKED_RB_PROFILE, 2),
)


def round_order(entries: Sequence[RoundEntry]) -> list[RoundEntry]:
    """The runs of a round in order, each entry's spread evenly over it and the
    entries' starts staggered, so that the heavy runs fall apart among the light."""
    slots = sorted(
        ((i + (n + 1) / (len(entries) + 1)) / e.runs, n, i)
        for n, e in enumerate(entries)
        for i in range(e.runs)
    )
    return [entries[n] for _, n, _ in slots]


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
    # in a monitor check, the one port of each unit whose waves are measured
    shown_ports: tuple[str, ...] = ()
    # whether the windows return every iteration rather than their mean
    raw: bool = False
    # the name of the kind of run it was drawn as; empty when drawn from one profile
    kind: str = ""


@dataclass(frozen=True)
class RunFailure:
    run: int
    # "refused" before it started; "run" when an instrument failed; "timeout";
    # "unavailable" when a unit could not be reached, the run aborted everywhere;
    # "connection" when the call was lost on the way; "wrong" when a monitor
    # captured otherwise than was sent; "delay" when a port's delay to its monitor
    # could not be measured; "error" for anything else
    kind: str
    detail: str


@dataclass(frozen=True)
class RunTiming:
    run: int
    kind: str
    # Unix time the run began at
    started_at: float
    # seconds each step took, in order; the step a run failed in is the last
    steps: dict[str, float]
    waves: int
    iterations: int
    raw: bool
    # None when the run completed, else its failure's kind, "refused" included
    failure: str | None


@dataclass
class SoakReport:
    unit_labels: list[str]
    runs: int = 0
    completed: int = 0
    refused: Counter[str] = field(default_factory=Counter)
    failures: list[RunFailure] = field(default_factory=list)
    timings: list[RunTiming] = field(default_factory=list)

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


def _fill_spans_at_once(
    rng: np.random.Generator, profile: SoakProfile
) -> tuple[np.ndarray, np.ndarray]:
    """Starts and lengths of waves over the span, as ``_fill_span`` lays them, drawn
    with numpy at once for the tens of thousands a packed run holds."""
    max_gap = int(rng.choice(profile.max_gap_ticks))
    first = 0 if rng.random() < 0.5 else _draw_ticks(rng, max_gap)
    n = profile.span_ticks // min(profile.wave_ticks) + 1
    lengths = rng.choice(np.asarray(profile.wave_ticks), size=n)
    gaps = np.maximum(
        4, np.round(np.exp(rng.uniform(0.0, math.log(max_gap), size=n)) / 4) * 4
    ).astype(int)
    gaps[rng.random(n) < profile.zero_gap_probability] = 0
    starts = first + np.concatenate(([0], np.cumsum(lengths + gaps)[:-1]))
    fits = starts + lengths <= profile.span_ticks
    return starts[fits], lengths[fits]


def _packed_waves(
    rng: np.random.Generator, profile: SoakProfile, job_ticks: int
) -> tuple[Wave, ...]:
    starts, lengths = [], []
    for j in range(profile.jobs):
        s, n = _fill_spans_at_once(rng, profile)
        starts.append(j * job_ticks + s)
        lengths.append(n)
    start = np.concatenate(starts) * TICK_NS
    length = np.concatenate(lengths) * TICK_NS
    gain = rng.uniform(profile.min_gain, profile.max_gain, size=len(start))
    phase = rng.uniform(0.0, 360.0, size=len(start))
    return tuple(
        Wave(float(a), float(b), float(c), float(d))
        for a, b, c, d in zip(start, length, gain, phase, strict=True)
    )


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
    job_ticks = profile.span_ticks + profile.readout_ticks + profile.job_blank_ticks
    waves: dict[str, tuple[Wave, ...]] = {}
    for port in port_ids:
        if profile.jobs > 1:
            waves[port] = _packed_waves(rng, profile, job_ticks)
            continue
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
        if profile.readout_ticks:
            spans = [
                (j * job_ticks + profile.span_ticks, profile.readout_ticks)
                for j in range(profile.jobs)
            ]
        else:
            spans = _fill_span(
                rng, lambda: _draw_ticks(rng, profile.max_window_ticks), profile
            )
        windows[port] = tuple(
            Window(start_ns=start * TICK_NS, length_ns=length * TICK_NS)
            for start, length in spans
        )

    length_ns = (profile.jobs * job_ticks - profile.job_blank_ticks) * TICK_NS
    iteration_blank_ns = float(rng.choice(profile.iteration_blank_ns))
    iterations = int(rng.choice(profile.iterations))
    shown_port = str(rng.choice(list(port_ids)))
    raw = profile.raw_share > 0 and rng.random() < profile.raw_share
    if raw:
        iterations = int(rng.choice(profile.raw_iterations))
    max_capture_ns = profile.max_raw_capture_ns if raw else profile.max_total_capture_ns
    for port, train in windows.items():
        kept: list[Window] = []
        for window in train:
            total_ns = sum(w.length_ns for w in kept) + window.length_ns
            if iterations * total_ns > max_capture_ns:
                break
            kept.append(window)
        windows[port] = tuple(kept)
    return RunPlan(
        run=run,
        length_ns=length_ns,
        iterations=iterations,
        iteration_blank_ns=iteration_blank_ns,
        shown_port=shown_port,
        waves=waves,
        windows=windows,
        raw=raw,
    )


def draw_run(
    rng: np.random.Generator,
    run: int,
    port_ids: Sequence[str],
    profile: SoakProfile | Sequence[RoundEntry] = DEFAULT_ROUND,
    capture_port_ids: Sequence[str] = (),
) -> RunPlan:
    """Draw one run as ``draw_plan`` does; given a round, from the kind whose place
    in the round ``run`` is."""
    if isinstance(profile, SoakProfile):
        return draw_plan(rng, run, port_ids, profile, capture_port_ids)
    order = round_order(profile)
    entry = order[run % len(order)]
    plan = draw_plan(rng, run, port_ids, entry.profile, capture_port_ids)
    return dataclasses.replace(plan, kind=entry.kind)


def _first_profile(profile: SoakProfile | Sequence[RoundEntry]) -> SoakProfile:
    return profile if isinstance(profile, SoakProfile) else profile[0].profile


def _settings_of(profile: SoakProfile | Sequence[RoundEntry]) -> object:
    if isinstance(profile, SoakProfile):
        return asdict(profile)
    return [
        {"kind": e.kind, "runs": e.runs, "profile": asdict(e.profile)} for e in profile
    ]


def _wave_samples(
    length_samples: int, marker_samples: int, shown: bool, check: bool = False
) -> np.ndarray:
    if check:
        return np.full(length_samples, 1.0 if shown else 0.0, dtype=complex)
    samples = np.full(length_samples, HIDDEN_AMPLITUDE, dtype=complex)
    if shown:
        samples[:marker_samples] = 1.0
    return samples


def build_directives(
    plan: RunPlan,
    emit_infos: dict[str, InstrumentInfo],
    *,
    check: bool = False,
) -> dict[str, SetFixedTimeline]:
    """One timeline per instrument alias, all sharing the run's length. With
    ``check``, the ports in ``plan.shown_ports`` send their waves at full scale and
    every other port sends waves of nothing."""
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
        shown = port in plan.shown_ports if check else port == plan.shown_port
        for wave in train:
            length_samples = round(wave.length_ns / period_ns)
            name = f"{alias}_{length_samples}"
            seq.register_waveform(
                name,
                _wave_samples(length_samples, marker_samples, shown, check),
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


def monitor_shot(plan: RunPlan, shown_port: str, monitor: str) -> shots.Shot:
    """What the monitor of the shown port's unit was sent in a monitor check."""
    return shots.Shot(
        pulses=tuple(
            shots.Pulse(
                w.start_ns,
                gain=w.gain,
                phase_deg=w.phase_deg,
                shape=shots.Shape("rect", w.length_ns),
                source=shown_port,
            )
            for w in plan.waves[shown_port]
        ),
        windows=tuple(
            shots.Window(f"cap{i}", w.start_ns, w.length_ns)
            for i, w in enumerate(plan.windows.get(monitor, ()))
        ),
        iterations=plan.iterations,
        raw=plan.raw,
        label=f"run {plan.run}, {_monitor.port_name(ResourceId(shown_port))} shown",
    )


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


def _role(port: ResourceId, check: bool) -> InstrumentRole:
    if str(port).endswith(_monitor.MON_PORT_SUFFIX):
        return InstrumentRole.RECEIVER
    if _is_capture_port(port) and not check:
        return InstrumentRole.TRANSCEIVER
    return InstrumentRole.TRANSMITTER


async def _deploy(
    client: QuelwareClient,
    emit_ports: Sequence[ResourceId],
    tx_hz: float,
    check: bool = False,
) -> dict[str, InstrumentInfo]:
    deployed: dict[str, InstrumentInfo] = {}
    async with _leased_session(client, emit_ports) as (session, _):

        async def _deploy_one(port: ResourceId) -> None:
            definition = InstrumentDefinition(
                alias=f"soak_{_monitor.port_name(port)}",
                mode=InstrumentMode.FIXED_TIMELINE,
                role=_role(port, check),
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
    directives: Mapping[str, Sequence[FixedTimelineDirective]],
    initialize: bool = False,
) -> tuple[RunFailure | None, dict[ResourceId, ResultContainer], dict[str, float]]:
    """Run one plan on every unit at once, configuring the units in parallel; no
    failure and the results when it completed, a refusal or a failure otherwise,
    with the seconds each step took. With ``initialize``, the instruments are
    initialized first."""
    period_ns = plan.length_ns + plan.iteration_blank_ns
    timeout_sec = plan.iterations * period_ns * 1e-9 + _WAIT_MARGIN_SEC
    laps: dict[str, float] = {}

    @contextlib.contextmanager
    def _timed(step: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        finally:
            laps[step] = time.monotonic() - start

    async def _configure_unit(aliases: list[str]) -> None:
        for alias in aliases:
            await drivers[alias].apply(directives[alias])

    try:
        if initialize:
            with _timed("initialize"):
                await session.initialize(ids)
        with _timed("configure"):
            await asyncio.gather(*(_configure_unit(a) for a in unit_aliases.values()))
        with _timed("trigger"):
            await session.trigger(ids)
        with _timed("wait"):
            results = await session.wait_for_results(ids, timeout_sec=timeout_sec)
    except Exception as e:
        return RunFailure(plan.run, *_classify(e)), {}, laps
    finally:
        logger.info(
            "run %d took %s (%d waves, iterations %d%s)",
            plan.run,
            ", ".join(f"{step} {sec:.3f} s" for step, sec in laps.items()),
            sum(len(t) for t in plan.waves.values()),
            plan.iterations,
            ", raw" if plan.raw else "",
        )
    return None, results, laps


def _judge_monitors(
    judge: correctness.Judge,
    plan: RunPlan,
    monitors: dict[UnitLabel, InstrumentInfo],
    results: dict[ResourceId, ResultContainer],
    *,
    measures_delay: bool = False,
) -> RunFailure | None:
    """A failure when a monitor captured otherwise than its unit's shown port sent;
    with ``measures_delay``, the run measures the delay of each shown port's path."""
    problems: list[str] = []
    for shown in plan.shown_ports:
        monitor = monitors[extract_unit_label(ResourceId(shown))]
        waves = results[monitor.id].iq_waveform_result
        shot = monitor_shot(plan, shown, str(monitor.port_id))
        problems += judge.check(
            correctness.Record(
                str(monitor.id),
                monitor.config.sampling_period_fs * 1e-6,
                dataclasses.replace(shot, measures_delay=measures_delay),
                {
                    name: (
                        np.stack([w.iq_array for w in waves[name]])
                        if plan.raw
                        else np.asarray(waves[name][0].iq_array)
                    )
                    for name in waves
                },
            )
        )
    if not problems:
        return None
    more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
    kind = "delay" if measures_delay else "wrong"
    return RunFailure(plan.run, kind, "; ".join(problems[:3]) + more)


async def _measure_delays(  # noqa: PLR0913
    session: Session,
    drivers: dict[str, FixedTimelineInstrumentDriver],
    unit_aliases: dict[UnitLabel, list[str]],
    ids: list[ResourceId],
    infos: dict[str, InstrumentInfo],
    emit_ports: Sequence[ResourceId],
    monitors: dict[UnitLabel, InstrumentInfo],
    judge: correctness.Judge,
    profile: SoakProfile | Sequence[RoundEntry],
) -> RunFailure | None:
    """Measure the delay from every emit port to its unit's monitor, one port of each
    unit at a time, as `correctness.delay_shot` does; a failure when one cannot be."""
    by_unit: dict[UnitLabel, list[str]] = {}
    for port in emit_ports:
        by_unit.setdefault(extract_unit_label(port), []).append(str(port))
    rounds = max(len(ports) for ports in by_unit.values())
    for k in range(rounds):
        shown = tuple(ports[k] for ports in by_unit.values() if k < len(ports))
        delay_shot = correctness.delay_shot(tolerance=judge.tolerance)
        (pulse,) = delay_shot.pulses
        (window,) = delay_shot.windows
        wave = Wave(pulse.start_ns, pulse.shape.length_ns, pulse.gain, pulse.phase_deg)
        plan = RunPlan(
            run=-1 - k,
            length_ns=_first_profile(profile).span_ticks * TICK_NS,
            iterations=delay_shot.iterations,
            iteration_blank_ns=_first_profile(profile).iteration_blank_ns[0],
            shown_port=shown[0],
            waves={str(p): (wave,) for p in emit_ports},
            windows={
                str(m.port_id): (Window(window.start_ns, window.length_ns),)
                for m in monitors.values()
            },
            shown_ports=shown,
        )
        mode = SetCaptureMode(mode=CaptureMode.AVERAGED_WAVEFORM)
        monitor_aliases = {m.definition.alias for m in monitors.values()}
        directives = {
            alias: [mode, timeline] if alias in monitor_aliases else [timeline]
            for alias, timeline in build_directives(plan, infos, check=True).items()
        }
        failure, results, _ = await _judge_run(
            session, drivers, unit_aliases, ids, plan, directives
        )
        if failure is None:
            failure = _judge_monitors(
                judge, plan, monitors, results, measures_delay=True
            )
        if failure is not None:
            return failure
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


def _write_timings(
    path: Path,
    report: SoakReport,
    emit_ports: Sequence[ResourceId],
    settings: dict[str, object],
    started_at: float,
) -> None:
    content = {
        "format": TIMINGS_FORMAT,
        "units": report.unit_labels,
        "ports": [str(p) for p in emit_ports],
        "settings": settings,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("quelware-tools", "quelware-client")
        },
        "started_at": started_at,
        "finished_at": time.time(),
        "runs": [asdict(t) for t in report.timings],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, indent=1) + "\n")
    except OSError:
        logger.exception("could not write the timings to %s", path)


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
    profile: SoakProfile | Sequence[RoundEntry] = DEFAULT_ROUND,
    tx_hz: float = 5.1e9,
    detune_hz: float = 0.0,
    save_dir: Path | None = None,
    stop_on_failure: bool = False,
    report_every: int = 100,
    discard_instruments: bool = False,
    initialize_each_run: bool = False,
    check_monitor: bool = False,
    tolerance: correctness.Tolerance = correctness.DEFAULT_TOLERANCE,
    timings_path: Path | None = None,
) -> SoakReport:
    """Run the soak test on the units until ``runs`` or ``duration_sec`` is spent.

    Every run goes on all the units at once, under one session and one trigger;
    ``unit_labels`` of None takes every unit the manager knows. With neither
    ``runs`` nor ``duration_sec`` it runs until interrupted. The units' tx/trx
    ports must be idle, unless ``discard_instruments`` is set. With
    ``initialize_each_run``, every run initializes the instruments before it
    configures them, as a client that starts each run afresh does. Each run is
    drawn from ``profile``, or, given a round of kinds, from the kind whose place in
    the round it is.

    With ``check_monitor``, every instrument on the units is discarded and the
    units are put in monitor loopback, which needs an admin PAT, and put back in
    open mode after; each run's monitor captures are judged within ``tolerance``.

    The instruments are deployed around ``tx_hz`` and set to ``tx_hz + detune_hz``,
    so a detune off their carrier has the units modulate the waves they send and
    demodulate what they capture.

    With ``timings_path``, the units, the ports, the settings, the versions of
    quelware-tools and quelware-client, and each run's timing are written there as
    JSON at the end, also when interrupted.
    """
    units = list(unit_labels) if unit_labels else await _find_units(client)
    report = SoakReport([str(u) for u in units])
    emit_ports: list[ResourceId] = []
    monitor_ports: list[ResourceId] = []
    judge = correctness.Judge(tolerance, keep_captures=False)
    started_at = time.time()
    started_monotonic = time.monotonic()
    try:
        if check_monitor:
            for unit in units:
                await _monitor.discard_unit_instruments(client, unit)
                await _monitor.set_monitor_loopback(client, unit)
                monitor_ports.append(await _monitor.monitor_port(client, unit))
        elif discard_instruments:
            ports = [p for unit in units for p in await _monitor.port_ids(client, unit)]
            logger.info(
                "discarding the instruments on %d ports of %d units",
                len(ports),
                len(units),
            )
            await _discard(client, ports)
        for unit in units:
            emit_ports += sorted(await _monitor.emit_ports(client, unit), key=str)
        emit_infos = await _deploy(client, emit_ports, tx_hz, check_monitor)
        monitor_infos = await _deploy(client, monitor_ports, tx_hz, check_monitor)
        monitors = {extract_unit_label(i.id): i for i in monitor_infos.values()}
        infos = emit_infos | monitor_infos
        capture_ports = (
            list(monitor_infos)
            if check_monitor
            else [p for p in emit_infos if _is_capture_port(p)]
        )
        logger.info(
            "soak test on %d units, %d emit ports, %d of them capturing",
            len(units),
            len(emit_ports),
            len(capture_ports),
        )

        ids = [info.id for info in infos.values()]
        unit_aliases: dict[UnitLabel, list[str]] = {}
        for info in infos.values():
            unit_aliases.setdefault(extract_unit_label(info.id), []).append(
                info.definition.alias
            )
        async with _leased_session(client, ids) as (session, lease):
            drivers = {
                info.definition.alias: create_instrument_driver_fixed_timeline(
                    session, info
                )
                for info in infos.values()
            }

            async def _set_up(port: ResourceId) -> None:
                alias = infos[str(port)].definition.alias
                await drivers[alias].apply([SetFrequency(hz=tx_hz + detune_hz)])

            capture_aliases = {infos[p].definition.alias for p in capture_ports}

            await _per_unit([*emit_ports, *monitor_ports], _set_up)
            if check_monitor:
                failure = await _measure_delays(
                    session,
                    drivers,
                    unit_aliases,
                    ids,
                    infos,
                    emit_ports,
                    monitors,
                    judge,
                    profile,
                )
                if failure is not None:
                    report.failures.append(failure)
                    logger.error("could not measure the delays: %s", failure.detail)
                    return report

            run = start_run
            while (runs is None or report.runs < runs) and (
                duration_sec is None
                or time.monotonic() - started_monotonic < duration_sec
            ):
                if lease.done():
                    exc = lease.exception()
                    failure = RunFailure(run, "lease", f"{type(exc).__name__}: {exc}")
                    report.failures.append(failure)
                    logger.error("lease lost before run %d: %s", run, failure.detail)
                    break
                rng = np.random.default_rng([seed, run])
                plan = draw_run(rng, run, list(emit_infos), profile, capture_ports)
                if check_monitor:
                    plan = dataclasses.replace(
                        plan, shown_ports=_draw_shown(rng, emit_ports)
                    )
                mode = SetCaptureMode(
                    mode=CaptureMode.RAW_WAVEFORMS
                    if plan.raw
                    else CaptureMode.AVERAGED_WAVEFORM
                )
                directives = {
                    alias: [mode, timeline] if alias in capture_aliases else [timeline]
                    for alias, timeline in build_directives(
                        plan, infos, check=check_monitor
                    ).items()
                }
                run_started_at = time.time()
                failure, results, laps = await _judge_run(
                    session,
                    drivers,
                    unit_aliases,
                    ids,
                    plan,
                    directives,
                    initialize=initialize_each_run,
                )
                if failure is None and check_monitor:
                    failure = _judge_monitors(judge, plan, monitors, results)
                report.timings.append(
                    RunTiming(
                        run=run,
                        kind=plan.kind,
                        started_at=run_started_at,
                        steps=laps,
                        waves=sum(len(t) for t in plan.waves.values()),
                        iterations=plan.iterations,
                        raw=plan.raw,
                        failure=None if failure is None else failure.kind,
                    )
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
        if timings_path is not None:
            _write_timings(
                timings_path,
                report,
                emit_ports,
                {
                    "seed": seed,
                    "start_run": start_run,
                    "profile": _settings_of(profile),
                    "tx_hz": tx_hz,
                    "detune_hz": detune_hz,
                    "check_monitor": check_monitor,
                    "initialize_each_run": initialize_each_run,
                },
                started_at,
            )
        if check_monitor:
            for unit in units:
                deployed = [
                    p
                    for p in [*emit_ports, *monitor_ports]
                    if extract_unit_label(p) == unit
                ]
                try:
                    await _monitor.restore_monitor_open(client, unit, deployed)
                except Exception:
                    logger.exception("could not put %s back in open mode", unit)
        elif emit_ports:
            try:
                await _discard(client, emit_ports)
            except Exception:
                logger.exception("could not discard the soak test's instruments")


def _draw_shown(
    rng: np.random.Generator, emit_ports: Sequence[ResourceId]
) -> tuple[str, ...]:
    """One port of each unit, whose waves its monitor is to receive."""
    by_unit: dict[UnitLabel, list[str]] = {}
    for port in emit_ports:
        by_unit.setdefault(extract_unit_label(port), []).append(str(port))
    return tuple(str(rng.choice(ports)) for ports in by_unit.values())


__all__ = [
    "DEFAULT_ROUND",
    "DENSE_CR_PROFILE",
    "HIDDEN_AMPLITUDE",
    "MARKER_TICKS",
    "PACKED_RB_PROFILE",
    "PACKED_SWEEP_PROFILE",
    "SPECTROSCOPY_PROFILE",
    "TICK_NS",
    "TIMINGS_FORMAT",
    "RoundEntry",
    "RunFailure",
    "RunPlan",
    "RunTiming",
    "SoakProfile",
    "SoakReport",
    "Wave",
    "Window",
    "build_directives",
    "draw_plan",
    "draw_run",
    "monitor_shot",
    "round_order",
    "run_soak_test",
]
