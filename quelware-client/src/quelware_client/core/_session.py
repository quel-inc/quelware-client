import asyncio
import logging
import math
from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
from types import TracebackType
from typing import cast

from quelware_core.entities.instrument import InstrumentDefinition, InstrumentInfo
from quelware_core.entities.resource import (
    ResourceId,
    extract_unit_label,
)
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer
from quelware_client.core.exceptions import (
    InitializeFailedError,
    NotTriggeredError,
    RunFailedError,
    ServiceUnavailableError,
    UnitBusyError,
)
from quelware_client.core.trigger_count_proposer import (
    FixedOffsetTriggerCountProposer,
    TriggerCountProposer,
)

from ._utils import create_unit_to_ids_map

logger = logging.getLogger(__name__)

_default_count_proposer = FixedOffsetTriggerCountProposer(grid_step=32, offset=0)
_CLOCK_FREQUENCY_HZ = 312_500_000
_FALLBACK_MIN_WAIT_MS = 500


class Session:
    """A lease over a set of resources on a QuEL system.

    Opening a session locks its resources on the server and yields a `token`
    used for subsequent operations such as deploying instruments and
    triggering. Create sessions with `QuelwareClient.create_session()` and use
    them as an async context manager, so they are opened on entry and closed on
    exit:

    ```python
    async with qc.create_session(["unit0:port0"]) as session:
        await session.deploy_instruments("unit0:port0", definitions)
        await session.trigger(instrument_ids)
        results = await session.wait_for_results(instrument_ids)
    ```

    Within a session, each unit has at most one run. A new trigger on a unit
    replaces its run, and initializing an instrument on the unit clears it.
    Other sessions on the same unit have their own runs. The session remembers
    which instruments were in the last trigger on each unit, and waits only for
    those. Another `Session` object built with the same token does not share
    this record.
    """

    def __init__(  # noqa: PLR0913
        self,
        resource_ids: Collection[ResourceId],
        agent: AgentContainer,
        ttl_ms: int = 4000,
        tentative_ttl_ms: int = 1000,
        token: SessionToken | None = None,
        trigger_count_proposer: TriggerCountProposer | None = None,
        skip_lock_check: bool = False,
    ):
        """Build a session over a set of resources.

        Normally created by `QuelwareClient.create_session()` rather than
        directly.

        Args:
            resource_ids: Resources to lock for the session.
            agent: Container providing the session and per-unit agents.
            ttl_ms: Time-to-live, in milliseconds, of the committed lease.
            tentative_ttl_ms: Time-to-live, in milliseconds, of the tentative
                lease held while opening.
            token: Pre-existing session token, if resuming a session.
            trigger_count_proposer: Strategy for choosing the clock count of a
                synchronized multi-unit trigger. Defaults to a fixed-offset
                proposer aligned to a 32-count grid.
            skip_lock_check: When True, skip verifying that the requested
                resources are locked after opening.
        """
        self._rsrc_ids = set(resource_ids)
        self._ttl_ms = ttl_ms
        self._tentative_ttl_ms = tentative_ttl_ms
        self._agent = agent
        self._token = token
        if trigger_count_proposer is None:
            trigger_count_proposer = _default_count_proposer
        self._trigger_count_proposer = trigger_count_proposer

        self._unit_to_ids: dict[UnitLabel, list[ResourceId]] = {}
        for rid in self._rsrc_ids:
            ul = extract_unit_label(rid)
            self._unit_to_ids.setdefault(ul, []).append(rid)

        self._check_lock = not skip_lock_check
        # instruments in the last trigger on each unit of this session
        self._triggered: set[ResourceId] = set()
        # units where a trigger or initialize of this session is running now
        self._busy_units: set[UnitLabel] = set()

    async def open(self):
        """Open the session, locking its resources and obtaining a token.

        Unless lock checking is disabled, this also verifies that every
        requested resource is actually locked.

        Raises:
            ValueError: If some requested resources could not be locked.
        """
        token, _ = await self._agent.session.open_session(
            self._rsrc_ids,
            tentative_ttl_ms=self._tentative_ttl_ms,
            committed_ttl_ms=self._ttl_ms,
        )
        self._token = token
        if self._check_lock:
            await self._ensure_target_resources_locked()
        logger.info(f"Session opened successfully. session_token={token}")

    async def _ensure_target_resources_locked(self):
        units = list(self._unit_to_ids.keys())

        tasks = [
            self._agent.resource(unit).list_locked_resources(self.token)
            for unit in units
        ]
        results = await asyncio.gather(*tasks)

        not_locked = []
        for unit, locked_rids in zip(units, results, strict=True):
            locked_rids = cast(list[ResourceId], locked_rids)
            target_rids = self._unit_to_ids[unit]
            locked_set = set(locked_rids)
            for target_rid in target_rids:
                if target_rid not in locked_set:
                    not_locked.append(target_rid)
        if not_locked:
            raise ValueError(f"Some resources are not locked: {not_locked}")

    @property
    def available_resource_ids(self) -> set[ResourceId]:
        """The set of resource ids this session was created for."""
        return self._rsrc_ids.copy()

    @property
    def unit_labels(self) -> list[UnitLabel]:
        """The labels of the units spanned by this session's resources."""
        return list(self._unit_to_ids)

    @property
    def agent_container(self) -> AgentContainer:
        """The underlying container of agents used by this session."""
        return self._agent

    @property
    def token(self) -> SessionToken:
        """The session token obtained when the session was opened.

        Raises:
            ValueError: If the session has not been opened yet.
        """
        if self._token is None:
            raise ValueError("Token not found. Session may not opened.")
        return self._token

    async def close(self):
        """Close the session and release its resources."""
        await self._agent.session.close_session(self.token)
        logger.info(f"Session closed. session_token={self.token}")

    async def extend(self, new_ttl_ms: int) -> bool:
        """Extend the session's lease.

        Args:
            new_ttl_ms: New time-to-live, in milliseconds, from now.

        Returns:
            True if the server accepted the extension.
        """
        success = await self._agent.session.extend_session(self.token, new_ttl_ms)
        logger.info(
            f"Session extended. session_token={self.token} new_ttl_ms={new_ttl_ms}"
        )
        return success

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ):
        await self.close()

    async def deploy_instruments(
        self,
        port_id: str | ResourceId,
        definitions: Collection[InstrumentDefinition],
        append: bool = False,
    ) -> list[InstrumentInfo]:
        """Deploy instrument definitions onto a port.

        Each definition's alias is automatically prefixed with the port's unit
        label, so the aliases passed in must not contain a ``':'``.

        Args:
            port_id: Port to deploy onto. Its unit label selects the unit.
            definitions: Instrument definitions to deploy.
            append: When True, add to the port's existing instruments instead
                of replacing them.

        Returns:
            Information about the deployed instruments.

        Raises:
            ValueError: If any definition's alias contains a ``':'``.
        """
        port_id = ResourceId(port_id)
        unit_label = extract_unit_label(port_id)
        prefixed_definitions = []
        for d in definitions:
            if ":" in d.alias:
                raise ValueError(f"alias must not contain ':' (got '{d.alias}')")
            prefixed = InstrumentDefinition(
                alias=f"{unit_label}:{d.alias}",
                mode=d.mode,
                role=d.role,
                profile=d.profile,
            )
            prefixed_definitions.append(prefixed)
        insts = await self._agent.resource(unit_label).deploy_instruments(
            port_id, prefixed_definitions, append, self.token
        )
        return insts

    async def discard_instruments(self, port_id: str | ResourceId) -> None:
        """Remove all instruments deployed on a port.

        Args:
            port_id: Port whose instruments to discard. Its unit label selects
                the unit.
        """
        port_id = ResourceId(port_id)
        unit_label = extract_unit_label(port_id)
        await self._agent.resource(unit_label).discard_instruments(port_id, self.token)

    async def configure_unit(
        self, unit_label: UnitLabel, controls: Mapping[str, str]
    ) -> dict[str, str]:
        """Apply unit-wide controls to a unit and return the resulting values.

        The session must hold locks on every port of ``unit_label`` and carry
        the required capability; the unit must have no deployed instruments.

        Args:
            unit_label: The unit to configure.
            controls: Vendor-namespaced control key/values to apply.

        Returns:
            The unit's control values after applying the change.
        """
        return await self._agent.worker(unit_label).configure_unit(controls, self.token)

    async def trigger(
        self,
        instrument_ids: Collection[ResourceId],
        wait_ms: int | None = None,
    ) -> int:
        """Arm the given instruments, then trigger them.

        Arming puts the configuration of each instrument on its unit's device,
        as the run of the session there. Then the server schedules a trigger,
        at which every unit starts. If the server's trigger service is
        unavailable, the client triggers the units itself: a self-timed trigger
        for a single unit, or a clock-synchronized trigger across several.

        Args:
            instrument_ids: Instruments to trigger.
            wait_ms: Delay, in milliseconds, from now to when the run starts,
                giving every unit time to start on it. ``None`` leaves it to
                the server, which also raises a wait shorter than it allows.
                When the client triggers the units itself, it waits at least
                500 ms.

        Returns:
            The clock count at which the trigger was scheduled.

        Raises:
            UnitBusyError: Immediately, if a trigger or initialize of this
                session is already running on one of the units.
        """
        unit_to_ids = create_unit_to_ids_map(instrument_ids)
        with self._claiming(unit_to_ids):
            # arming replaces the session's run on the unit, so forget the old
            # one now, even if this trigger fails
            self._forget_runs_on(unit_to_ids)
            scheduled = await self._arm_and_trigger(
                instrument_ids, unit_to_ids, wait_ms
            )
            self._triggered.update(instrument_ids)
        return scheduled

    async def _arm_and_trigger(
        self,
        instrument_ids: Collection[ResourceId],
        unit_to_ids: dict[UnitLabel, list[ResourceId]],
        wait_ms: int | None,
    ) -> int:
        logger.info(f"starting arming (token= {self.token} )")
        arm_coros = [
            self._agent.instrument(unit_label).arm(self.token, ids)
            for unit_label, ids in unit_to_ids.items()
        ]
        await asyncio.gather(*arm_coros)
        logger.info(f"finished arming (token= {self.token} )")

        try:
            scheduled = await self._agent.trigger.trigger(
                self.token,
                list(instrument_ids),
                requested_min_wait_ms=wait_ms,
            )
            logger.info(f"trigger scheduled via manager at clock_count={scheduled}")
            return scheduled
        except ServiceUnavailableError:
            fallback_wait_ms = max(wait_ms or 0, _FALLBACK_MIN_WAIT_MS)
            logger.warning(
                f"Manager-side TriggerService unavailable; falling back to "
                f"client-side trigger (wait_ms={fallback_wait_ms})."
            )

        return await self._client_side_trigger_fallback(unit_to_ids, fallback_wait_ms)

    async def wait_for_results(
        self,
        instrument_ids: Collection[ResourceId],
        timeout_sec: float | None = None,
    ) -> dict[ResourceId, ResultContainer]:
        """Wait for the result of every one of the instruments of a run.

        Pass the instruments given to `trigger()`. An instrument without a
        capture window is waited for too, and its result is empty. Only the
        instruments in the last trigger on each unit can be waited for, and not
        after an instrument on that unit is initialized.

        Args:
            instrument_ids: Instruments to wait for.
            timeout_sec: Bound on the whole wait; ``None`` waits without limit.

        Returns:
            Each instrument's result.

        Raises:
            NotTriggeredError: Immediately, if an instrument was not in the last
                trigger on its unit.
            RunFailedError: If any instrument failed, once all of them have
                finished, with the error of each that failed and the results of
                the others.
            TimeoutError: If some are still running when ``timeout_sec`` runs out.
        """
        self._ensure_triggered(instrument_ids)
        tasks = {
            asyncio.ensure_future(
                self._agent.instrument(extract_unit_label(rid)).wait_for_result(
                    self.token, rid, None
                )
            ): rid
            for rid in instrument_ids
        }
        if not tasks:
            return {}
        try:
            done, pending = await asyncio.wait(tasks, timeout=timeout_sec)
        finally:
            for task in tasks:
                task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            running = sorted(tasks[task] for task in pending)
            raise TimeoutError(f"Instruments still running: {running}")

        results: dict[ResourceId, ResultContainer] = {}
        failures: dict[ResourceId, BaseException] = {}
        for task in done:
            if (err := task.exception()) is not None:
                failures[tasks[task]] = err
            else:
                results[tasks[task]] = task.result()
        if failures:
            raise RunFailedError(failures, results)
        return results

    async def initialize(
        self, instrument_ids: Collection[ResourceId], parallel: bool = True
    ) -> None:
        """Initialize the given instruments.

        An initialized instrument is empty: armed, it plays and captures
        nothing until it is given a timeline again. This also clears the
        session's run on each of their units: no instrument on those units can
        be waited for until the next trigger there.

        Args:
            instrument_ids: Instruments to initialize.
            parallel: Initialize the units at the same time, the default; when
                False, one unit after another. Either way every unit is
                initialized, also after one fails, and the instruments of one
                unit are always initialized in one call.

        Raises:
            UnitBusyError: Immediately, if a trigger or initialize of this
                session is already running on one of the units.
            InitializeFailedError: If some units failed, once every unit has
                finished, with the error of each unit that failed.
        """
        unit_to_ids = create_unit_to_ids_map(instrument_ids)
        with self._claiming(unit_to_ids):
            self._forget_runs_on(unit_to_ids)
            if parallel:
                # wait for every unit, so that none is still initializing once
                # the units are let go
                outcomes = await asyncio.gather(
                    *(
                        self._initialize_unit(unit_label, ids)
                        for unit_label, ids in unit_to_ids.items()
                    )
                )
            else:
                outcomes = [
                    await self._initialize_unit(unit_label, ids)
                    for unit_label, ids in unit_to_ids.items()
                ]
            failures = {
                unit_label: outcome
                for unit_label, outcome in zip(unit_to_ids, outcomes, strict=True)
                if outcome is not None
            }
            if failures:
                raise InitializeFailedError(failures, len(unit_to_ids))

    async def _initialize_unit(
        self, unit_label: UnitLabel, instrument_ids: list[ResourceId]
    ) -> Exception | None:
        """Initialize the instruments of a unit, and return its error, if any."""
        try:
            await self._agent.instrument(unit_label).initialize(
                self.token, instrument_ids
            )
        except Exception as e:
            return e
        return None

    async def fetch_result(self, instrument_id: ResourceId) -> ResultContainer:
        """Fetch the result of one instrument, with a single request.

        Unlike `wait_for_result()`, this does not retry when the request times
        out.

        Raises:
            NotTriggeredError: Immediately, if the instrument was not in the last
                trigger on its unit.
        """
        self._ensure_triggered([instrument_id])
        agent = self._agent.instrument(extract_unit_label(instrument_id))
        return await agent.fetch_result(self.token, instrument_id)

    async def wait_for_result(
        self, instrument_id: ResourceId, timeout_sec: float | None = None
    ) -> ResultContainer:
        """Wait for the result of one instrument.

        Unlike `wait_for_results()`, this raises the instrument's own error if
        it failed.

        Args:
            instrument_id: Instrument to wait for.
            timeout_sec: Maximum time to wait; ``None`` waits without limit.

        Raises:
            NotTriggeredError: Immediately, if the instrument was not in the last
                trigger on its unit.
        """
        self._ensure_triggered([instrument_id])
        agent = self._agent.instrument(extract_unit_label(instrument_id))
        return await agent.wait_for_result(self.token, instrument_id, timeout_sec)

    @contextmanager
    def _claiming(self, unit_labels: Collection[UnitLabel]) -> Iterator[None]:
        """Mark the units as busy during a trigger or initialize.

        Two of them at the same time on one unit would make the record of
        triggered instruments wrong.
        """
        units = set(unit_labels)
        if busy := sorted(units & self._busy_units):
            raise UnitBusyError().with_unit_labels(busy)
        self._busy_units |= units
        try:
            yield
        finally:
            self._busy_units -= units

    def _forget_runs_on(self, unit_labels: Collection[UnitLabel]) -> None:
        """Forget the triggered instruments on the units."""
        units = set(unit_labels)
        self._triggered = {
            rid for rid in self._triggered if extract_unit_label(rid) not in units
        }

    def _ensure_triggered(self, instrument_ids: Collection[ResourceId]) -> None:
        """Raise if an instrument was not in the last trigger on its unit.

        Raises:
            NotTriggeredError: With the ids of those instruments.
        """
        missing = sorted(set(instrument_ids) - self._triggered)
        if missing:
            raise NotTriggeredError().with_resource_ids(missing)

    async def _client_side_trigger_fallback(
        self,
        unit_to_ids: dict[UnitLabel, list[ResourceId]],
        wait_ms: int,
    ) -> int:
        if len(unit_to_ids) == 1:
            unit_label = next(iter(unit_to_ids))
            logger.info(
                f"fallback: self-timed trigger (unit={unit_label}, wait_ms={wait_ms})"
            )
            scheduled = await self._agent.instrument(unit_label).trigger_now(
                self.token, wait_ms
            )
            logger.info(f"trigger scheduled at clock_count={scheduled}")
            return scheduled

        logger.info(
            f"fallback: multi-unit sync trigger "
            f"(n_units={len(unit_to_ids)}, wait_ms={wait_ms})"
        )
        reference_unit = next(iter(unit_to_ids))
        cur, ref = await self._agent.worker(reference_unit).get_clock_snapshot()
        wait_count = math.ceil(wait_ms * _CLOCK_FREQUENCY_HZ / 1000)
        target_time = self._trigger_count_proposer.propose_count(cur, ref, wait_count)
        trigger_coros = [
            self._agent.instrument(unit_label).schedule_trigger(self.token, target_time)
            for unit_label in unit_to_ids
        ]
        await asyncio.gather(*trigger_coros)
        logger.info(f"trigger scheduled at clock_count={target_time}")
        return target_time
