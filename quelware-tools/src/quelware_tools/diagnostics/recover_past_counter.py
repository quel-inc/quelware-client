"""Bring a unit back to normal after a run that failed with past_counter.

After such a run, the unit may begin every later pulse with the end of an
earlier waveform, without reporting an error. As a workaround, this triggers
every port a few seconds ahead and cancels the run on purpose before it
starts, which brings the unit back to normal without a reboot. It is
temporary: an update of the units in the near future makes it unnecessary.

It replaces the instruments on every port of the unit and removes them at the
end, so run it only when nobody else uses the unit. A run reported late was
cancelled too late and sent one short, weak pulse; run it again with a longer
wait.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from grpclib import GRPCError
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core import QuelwareClient, Session
from quelware_client.core.exceptions import RunFailedError
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)
from quelware_core.entities import directives
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

logger = logging.getLogger(__name__)

DEFAULT_WAIT_MS = 5000
DEFAULT_CENTER_HZ = 5.1e9
_HALF_BAND_HZ = 0.5e6
# apart by more than one stream's effective band (80 %), so one carrier cannot
# cover both and the server takes a second stream
_SPLIT_OF_BANDWIDTH = 0.9
# lengths in timeline steps, which every sampling period divides
_PULSE_STEPS = 4
_PULSE_AMPLITUDE = 0.01
_CAPTURE_STEPS = 8
_SESSION_TTL_MS = 20_000
_WAIT_MARGIN_SEC = 10.0

_TX, _RX = InstrumentRole.TRANSMITTER, InstrumentRole.RECEIVER


@dataclass(frozen=True)
class Want:
    """One instrument to deploy: its role, and its band in half splits from the
    center (-1, 0 or +1)."""

    role: InstrumentRole
    offset: int


# what a port is tried with, most streams first, by the prefix of its name;
# trx before tx, which it starts with. Two instruments a split apart land on
# two streams; a port with one stream refuses them, and takes one.
_PLANS: dict[str, list[list[Want]]] = {
    "trx": [
        [Want(_TX, -1), Want(_TX, 1), Want(_RX, -1), Want(_RX, 1)],
        [Want(_TX, -1), Want(_TX, 1), Want(_RX, -1)],
        [Want(_TX, 0), Want(_RX, 0)],
    ],
    "tx": [
        [Want(_TX, -1), Want(_TX, 1)],
        [Want(_TX, 0)],
    ],
    "rx": [
        [Want(_RX, -1), Want(_RX, 1)],
        [Want(_RX, 0)],
    ],
}


@dataclass(frozen=True)
class RecoverReport:
    unit_labels: tuple[str, ...]
    ports: int
    instruments: int
    # aliases of the instruments whose run completed: the cancel came too late
    late: tuple[str, ...] = ()
    # instruments that failed for another reason, with the error
    failed: Mapping[str, str] = field(default_factory=dict)

    @property
    def cancelled(self) -> int:
        return self.instruments - len(self.late) - len(self.failed)

    @property
    def ok(self) -> bool:
        return not self.late and not self.failed


def plans_for(port_name: str) -> list[list[Want]]:
    """What a port is tried with, by its name; empty for a port that takes no
    instrument."""
    return next((p for k, p in _PLANS.items() if port_name.startswith(k)), [])


def definition(
    port_name: str, want: Want, center_hz: float, split_hz: float
) -> InstrumentDefinition:
    hz = center_hz + want.offset * split_hz / 2
    return InstrumentDefinition(
        alias=f"recover_{port_name}_{want.role.name.lower()}_{want.offset + 1}",
        mode=InstrumentMode.FIXED_TIMELINE,
        role=want.role,
        profile=FixedTimelineProfile(hz - _HALF_BAND_HZ, hz + _HALF_BAND_HZ),
    )


def split_hz(sampling_period_fs: int) -> float:
    """How far apart two instruments of a port are set, for its stream's band."""
    return _SPLIT_OF_BANDWIDTH * 1e15 / sampling_period_fs


def report_of(
    unit_labels: Sequence[str],
    ports: int,
    infos: Sequence[InstrumentInfo],
    failures: Mapping[ResourceId, BaseException],
) -> RecoverReport:
    """Tell the cancelled runs, which fail with the server's abort error, from
    the ones that completed and the ones that failed otherwise."""
    alias = {i.id: i.definition.alias for i in infos}
    late = tuple(alias[i.id] for i in infos if i.id not in failures)
    failed = {
        alias.get(rid, str(rid)): str(err)
        for rid, err in failures.items()
        if "abort" not in str(err).lower()
    }
    return RecoverReport(tuple(unit_labels), ports, len(infos), late, failed)


async def run_recover_past_counter(
    client: QuelwareClient,
    unit_labels: Sequence[UnitLabel],
    *,
    wait_ms: int = DEFAULT_WAIT_MS,
    center_hz: float = DEFAULT_CENTER_HZ,
) -> RecoverReport:
    """Trigger every port of the units ``wait_ms`` ahead and cancel the run
    before it starts.

    The instruments on every port of the units are discarded first, and the
    ones this deploys are removed before returning.
    """
    if not unit_labels:
        raise ValueError("name the units to recover")
    ports: list[ResourceId] = []
    for unit in unit_labels:
        ports += sorted(await _monitor.port_ids(client, unit), key=str)
    if not ports:
        raise RuntimeError(f"no port found on {', '.join(unit_labels)}")
    infos: list[InstrumentInfo] = []
    try:
        async with client.create_session(ports, ttl_ms=_SESSION_TTL_MS) as session:
            for port in ports:
                await session.discard_instruments(port)
            for port in ports:
                infos += await _deploy_port(session, port, center_hz)
        ids = [i.id for i in infos]
        async with client.create_session(ids, ttl_ms=_SESSION_TTL_MS) as session:
            for info in infos:
                await _configure(session, info)
            count = await session.trigger(ids, wait_ms=wait_ms)
            await session.abort_runs()
            logger.info("triggered %d instruments at %d and cancelled", len(ids), count)
            try:
                await session.wait_for_results(
                    ids, timeout_sec=wait_ms / 1000 + _WAIT_MARGIN_SEC
                )
                failures: Mapping[ResourceId, BaseException] = {}
            except RunFailedError as e:
                failures = e.failures
    finally:
        await _discard(client, ports)
    return report_of([str(u) for u in unit_labels], len(ports), infos, failures)


async def _deploy_port(
    session: Session, port: ResourceId, center_hz: float
) -> list[InstrumentInfo]:
    name = _monitor.port_name(port)
    plans = plans_for(name)
    if not plans:
        logger.info("%s: skipped, its name says no role", port)
        return []
    # one instrument first, for the stream's band the split is measured in
    (probe,) = await session.deploy_instruments(
        port, [definition(name, plans[-1][0], center_hz, 0.0)]
    )
    split = split_hz(probe.config.sampling_period_fs)
    for plan in plans:
        try:
            infos = await session.deploy_instruments(
                port, [definition(name, w, center_hz, split) for w in plan]
            )
        except GRPCError as e:
            logger.info("%s: %d instruments refused: %s", port, len(plan), e)
            continue
        logger.info("%s: %s", port, ", ".join(i.definition.alias for i in infos))
        return infos
    raise RuntimeError(f"{port}: no plan could be deployed")


async def _configure(session: Session, info: InstrumentInfo) -> None:
    alias = info.definition.alias
    config = info.config
    profile = info.definition.profile
    seq = Sequencer(default_sampling_period_ns=config.sampling_period_fs / 1e6)
    seq.bind(alias, config.sampling_period_fs, config.timeline_step_samples)
    settings: list[directives.FixedTimelineDirective] = [
        directives.SetFrequency(
            hz=(profile.frequency_range_min + profile.frequency_range_max) / 2
        )
    ]
    step = config.timeline_step_samples
    if info.definition.role is _TX:
        seq.register_waveform(
            "pulse", np.full(_PULSE_STEPS * step, _PULSE_AMPLITUDE, dtype=complex)
        )
        seq.add_event(alias, "pulse", start_offset_ns=0.0)
    else:
        length_ns = _CAPTURE_STEPS * step * config.sampling_period_fs / 1e6
        seq.add_capture_window(
            alias, "capture", start_offset_ns=0.0, length_ns=length_ns
        )
        settings.append(
            directives.SetCaptureMode(mode=directives.CaptureMode.AVERAGED_WAVEFORM)
        )
    settings.append(seq.export_set_fixed_timeline_directive(alias))
    driver = create_instrument_driver_fixed_timeline(session, info)
    await driver.initialize()
    await driver.apply(settings)


async def _discard(client: QuelwareClient, ports: Sequence[ResourceId]) -> None:
    async with client.create_session(list(ports), ttl_ms=_SESSION_TTL_MS) as session:
        for port in ports:
            await session.discard_instruments(port)


__all__ = [
    "DEFAULT_CENTER_HZ",
    "DEFAULT_WAIT_MS",
    "RecoverReport",
    "Want",
    "definition",
    "plans_for",
    "report_of",
    "run_recover_past_counter",
    "split_hz",
]
