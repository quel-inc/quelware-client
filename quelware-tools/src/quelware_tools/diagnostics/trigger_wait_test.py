"""Trigger wait test for live QuEL-3 units.

Puts a transmitter on every tx/trx port of the units, each sending one short
pulse, and triggers them all at once over and over, asking for each of a set of
waits between the trigger and the start in turn. A run passes if every
instrument completes it; one that fails, as when a stream was started past its
count (``past_counter``), counts against its wait. How often each wait fails
shows the least one the units start in time on, whatever the server does to get
there. The server raises a wait under its floor to the floor, so waits below it
are not tried as asked.

The instruments deployed are discarded before returning.
"""

import asyncio
import logging
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from grpclib import GRPCError
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core import QuelwareClient, Session
from quelware_client.core.exceptions import RunFailedError
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)
from quelware_core.entities.directives import SetFrequency
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

DEFAULT_WAITS_MS = (150, 175, 200, 250, 300, 400, 600)
_TICK_NS = 3.2
_PULSE_TICKS = 16
_PROFILE_HALF_HZ = 200e6
_SESSION_TTL_MS = 20_000
_LEASE_EXTEND_SEC = 5.0
_WAIT_MARGIN_SEC = 30.0
_CONCURRENT_DISCARDS = 32


@dataclass
class WaitResult:
    wait_ms: int
    runs: int = 0
    completed: int = 0
    # a failed run once per reason: "past_counter", another unit error, or the
    # kind of error the run broke on
    failures: Counter[str] = field(default_factory=Counter)
    trigger_sec: list[float] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return self.runs - self.completed


@dataclass(frozen=True)
class TriggerWaitReport:
    unit_labels: tuple[str, ...]
    ports: int
    results: tuple[WaitResult, ...]


def failure_reasons(error: Exception) -> set[str]:
    """What a run failed on: ``past_counter`` or ``unit error`` for each instrument
    whose unit flagged one, or else the kind of the error."""
    if isinstance(error, RunFailedError):
        reasons = set()
        for err in error.failures.values():
            text = str(err)
            reasons.add("past_counter" if "past_counter=True" in text else "unit error")
        return reasons
    if isinstance(error, GRPCError):
        return {error.status.name}
    return {type(error).__name__}


async def run_trigger_wait_test(
    client: QuelwareClient,
    unit_labels: Sequence[UnitLabel] | None = None,
    *,
    waits_ms: Sequence[int] = DEFAULT_WAITS_MS,
    runs_per_wait: int = 20,
    tx_hz: float = 5.1e9,
    discard_instruments: bool = False,
) -> TriggerWaitReport:
    """Trigger every tx/trx port of the units ``runs_per_wait`` times at each of
    ``waits_ms``, one wait after another in turn.

    ``unit_labels`` of None takes every unit the manager knows; one unit is
    triggered by itself, several through the manager. The units' tx/trx ports
    must be idle, unless ``discard_instruments`` is set.
    """
    units = list(unit_labels) if unit_labels else await _find_units(client)
    results = {w: WaitResult(w) for w in waits_ms}
    ports: list[ResourceId] = []
    try:
        for unit in units:
            ports += sorted(await _monitor.emit_ports(client, unit), key=str)
        if discard_instruments:
            await _discard(client, ports)
        infos = await _deploy(client, ports, tx_hz)
        ids = [info.id for info in infos]
        logger.info(
            "triggering %d ports of %d units %d times at each of %s ms",
            len(ports),
            len(units),
            runs_per_wait,
            list(waits_ms),
        )
        async with client.create_session(ids, ttl_ms=_SESSION_TTL_MS) as session:
            lease = asyncio.create_task(_keep_lease(session))
            try:
                await _configure(session, infos, tx_hz)
                for i in range(runs_per_wait):
                    for wait_ms in waits_ms:
                        if lease.done():
                            raise RuntimeError(f"lost the lease: {lease.exception()!r}")
                        await _run_once(session, ids, results[wait_ms])
                    logger.info("round %d of %d done", i + 1, runs_per_wait)
            finally:
                lease.cancel()
        return TriggerWaitReport(
            tuple(str(u) for u in units), len(ports), tuple(results.values())
        )
    finally:
        if ports:
            try:
                await _discard(client, ports)
            except Exception:
                logger.exception("could not discard the test's instruments")


async def _run_once(
    session: Session, ids: list[ResourceId], result: WaitResult
) -> None:
    result.runs += 1
    started = time.monotonic()
    try:
        await session.trigger(ids, wait_ms=result.wait_ms)
        result.trigger_sec.append(time.monotonic() - started)
        await session.wait_for_results(
            ids, timeout_sec=result.wait_ms / 1000 + _WAIT_MARGIN_SEC
        )
    except Exception as e:
        reasons = failure_reasons(e)
        result.failures.update(reasons)
        logger.warning("wait %d ms failed: %s", result.wait_ms, sorted(reasons))
        return
    result.completed += 1


async def _configure(
    session: Session, infos: Sequence[InstrumentInfo], tx_hz: float
) -> None:
    for info in infos:
        period_ns = info.config.sampling_period_fs / 1e6
        alias = info.definition.alias
        seq = Sequencer(default_sampling_period_ns=period_ns)
        seq.bind(
            alias, info.config.sampling_period_fs, info.config.timeline_step_samples
        )
        samples = round(_PULSE_TICKS * _TICK_NS / period_ns)
        seq.register_waveform("pulse", np.full(samples, 0.5, dtype=complex))
        seq.add_event(alias, "pulse", start_offset_ns=0.0)
        driver = create_instrument_driver_fixed_timeline(session, info)
        await driver.apply(
            [SetFrequency(hz=tx_hz), seq.export_set_fixed_timeline_directive(alias)]
        )


async def _deploy(
    client: QuelwareClient, ports: Sequence[ResourceId], tx_hz: float
) -> list[InstrumentInfo]:
    by_unit: dict[UnitLabel, list[ResourceId]] = {}
    for port in ports:
        by_unit.setdefault(extract_unit_label(port), []).append(port)
    deployed: dict[ResourceId, InstrumentInfo] = {}

    async def _deploy_unit(unit_ports: list[ResourceId]) -> None:
        for port in unit_ports:
            definition = InstrumentDefinition(
                alias=f"trigger_wait_{_monitor.port_name(port)}",
                mode=InstrumentMode.FIXED_TIMELINE,
                role=InstrumentRole.TRANSMITTER,
                profile=FixedTimelineProfile(
                    tx_hz - _PROFILE_HALF_HZ, tx_hz + _PROFILE_HALF_HZ
                ),
            )
            (deployed[port],) = await session.deploy_instruments(port, [definition])

    async with client.create_session(list(ports), ttl_ms=_SESSION_TTL_MS) as session:
        await asyncio.gather(*(_deploy_unit(p) for p in by_unit.values()))
    return [deployed[p] for p in ports]


async def _discard(client: QuelwareClient, ports: Sequence[ResourceId]) -> None:
    calls = asyncio.Semaphore(_CONCURRENT_DISCARDS)

    async def _discard_one(port: ResourceId) -> None:
        async with calls:
            await session.discard_instruments(port)

    async with client.create_session(list(ports), ttl_ms=_SESSION_TTL_MS) as session:
        await asyncio.gather(*(_discard_one(p) for p in ports))


async def _keep_lease(session: Session) -> None:
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


__all__ = [
    "DEFAULT_WAITS_MS",
    "TriggerWaitReport",
    "WaitResult",
    "failure_reasons",
    "run_trigger_wait_test",
]
