import asyncio
import logging
from collections.abc import Callable, Collection
from typing import TypeAlias, TypeVar, cast

from quelware_core.entities.instrument import InstrumentInfo
from quelware_core.entities.port import PortInfo
from quelware_core.entities.resource import (
    ResourceId,
    ResourceInfo,
    extract_unit_label,
)
from quelware_core.entities.unit import UnitLabel

from quelware_client.core._agent_container import AgentContainer
from quelware_client.core.interfaces.diagnostics_agent import DiagnosticsAgent
from quelware_client.core.interfaces.health_agent import HealthAgent
from quelware_client.core.interfaces.instrument_agent import InstrumentAgent
from quelware_client.core.interfaces.worker_agent import WorkerAgent

from ._session import Session
from .interfaces.resource_agent import ResourceAgent

logger = logging.getLogger(__name__)

A = TypeVar("A")
AgentFactory: TypeAlias = Callable[[UnitLabel], A]
"""Callable that builds a per-unit agent, given the unit's label."""
_ResourceId: TypeAlias = ResourceId | str


class QuelwareClient:
    """High-level entry point for working with a QuEL system.

    The client discovers the units that make up the system, runs an optional
    health check on each, and wires up the per-unit agents used to inspect
    resources and control instruments. Instances are normally created with
    `create_quelware_client()` and used as an async context manager, which
    starts the client on entry and closes the underlying gRPC channel on exit:

    ```python
    qc = create_quelware_client("192.0.2.1", 50051)
    async with qc:
        async with qc.create_session(["unit0:port0"]) as session:
            ...
    ```
    """

    def __init__(
        self,
        agent: AgentContainer,
        health_agent_factory: AgentFactory[HealthAgent] | None = None,
        resource_agent_factory: AgentFactory[ResourceAgent] | None = None,
        instrument_agent_factory: AgentFactory[InstrumentAgent] | None = None,
        diagnostics_agent_factory: AgentFactory[DiagnosticsAgent] | None = None,
        worker_agent_factory: AgentFactory[WorkerAgent] | None = None,
        close_handlers: list[Callable[[], None]] | None = None,
        skip_lock_check: bool = False,
    ):
        """Assemble a client from an agent container and per-unit factories.

        Most callers should use `create_quelware_client()` rather than
        constructing this directly.

        Args:
            agent: Container holding the system-wide agents (session,
                configuration, trigger).
            health_agent_factory: Builds a health agent per unit. When given,
                units that fail their health check are skipped during
                initialization.
            resource_agent_factory: Builds a resource agent per unit.
            instrument_agent_factory: Builds an instrument agent per unit.
            diagnostics_agent_factory: Builds a diagnostics agent per unit.
            worker_agent_factory: Builds a worker agent per unit.
            close_handlers: Callables run on `stop()`, e.g. to close the gRPC
                channel.
            skip_lock_check: When True, sessions created by this client skip
                verifying that their resources are locked after opening.
        """
        self._agent = agent
        self._health_agent_factory = health_agent_factory
        self._rsrc_agent_factory = resource_agent_factory
        self._inst_agent_factory = instrument_agent_factory
        self._diag_agent_factory = diagnostics_agent_factory
        self._worker_agent_factory = worker_agent_factory
        self._unit_labels: list[UnitLabel] = []
        self._close_handlers = close_handlers or []
        self._skip_lock_check = skip_lock_check

    @property
    def agent(self) -> AgentContainer:
        """The underlying container of system-wide and per-unit agents."""
        return self._agent

    async def start(self):
        """Initialize the client. Called on ``async with`` entry."""
        await self.initialize()

    async def stop(self):
        """Run the registered close handlers (e.g. close the gRPC channel)."""
        for handler in self._close_handlers:
            handler()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def initialize(self):
        """Discover the system's units and wire up their agents.

        Lists every unit in the system and, if a health-agent factory was
        provided, runs a health check on each and keeps only the healthy ones.
        Resource, instrument, diagnostics, and worker agents are then created
        for each retained unit, and `list_unit_labels()` reflects the result.

        Called automatically by `start()`; you rarely need to call it directly.
        """
        all_labels = await self._agent.system_configuration.list_units()

        if self._health_agent_factory:
            for ul in all_labels:
                self._agent.update_health_agent(ul, self._health_agent_factory(ul))
            results = await asyncio.gather(
                *(self._agent.health(ul).check() for ul in all_labels)
            )
            healthy_labels = []
            for ul, ok in zip(all_labels, results, strict=True):
                if ok:
                    logger.info("Passed initial health check on %s", ul)
                    healthy_labels.append(ul)
                else:
                    logger.warning("Health check on %s failed, skipping", ul)
        else:
            healthy_labels = list(all_labels)

        for ul in healthy_labels:
            if self._rsrc_agent_factory:
                self._agent.update_resource_agent(ul, self._rsrc_agent_factory(ul))
            if self._inst_agent_factory:
                self._agent.update_instrument_agent(ul, self._inst_agent_factory(ul))
            if self._diag_agent_factory:
                self._agent.update_diagnostics_agent(ul, self._diag_agent_factory(ul))
            if self._worker_agent_factory:
                self._agent.update_worker_agent(ul, self._worker_agent_factory(ul))
        self._unit_labels = healthy_labels

    def list_unit_labels(self) -> list[UnitLabel]:
        """Return the labels of the units retained after initialization."""
        return list(self._unit_labels)

    def create_session(
        self,
        resource_ids: Collection[_ResourceId],
        ttl_ms: int = 4000,
        tentative_ttl_ms: int = 1000,
    ) -> Session:
        """Create a session that leases the given resources.

        The returned session is not opened yet; open it with ``await
        session.open()`` or by using it as an async context manager.

        Args:
            resource_ids: Resources (e.g. ports) to lock for the session.
            ttl_ms: Time-to-live, in milliseconds, of the committed lease.
            tentative_ttl_ms: Time-to-live, in milliseconds, of the tentative
                lease held while the session is being opened.

        Returns:
            An unopened `Session` for the requested resources.
        """
        return Session(
            resource_ids=cast(list[ResourceId], resource_ids),
            agent=self._agent,
            ttl_ms=ttl_ms,
            tentative_ttl_ms=tentative_ttl_ms,
            skip_lock_check=self._skip_lock_check,
        )

    async def list_resource_infos(self) -> list[ResourceInfo]:
        """Return the resource information for every unit, aggregated."""
        coros = [
            self._agent.resource(ul).list_resource_infos() for ul in self._unit_labels
        ]
        results = await asyncio.gather(*coros)
        rsrc_infos: list[ResourceInfo] = []
        for res in results:
            rsrc_infos.extend(res)
        return rsrc_infos

    async def get_port_info(self, port_id: ResourceId) -> PortInfo:
        """Return information about a single port.

        Args:
            port_id: Identifier of the port; its unit label selects the unit
                to query.

        Returns:
            The port's information.
        """
        unit_label = extract_unit_label(port_id)
        port = await self._agent.resource(unit_label).get_port_info(port_id)
        return port

    async def get_instrument_info(self, instrument_id: ResourceId) -> InstrumentInfo:
        """Return information about a single instrument.

        Args:
            instrument_id: Identifier of the instrument; its unit label selects
                the unit to query.

        Returns:
            The instrument's information.
        """
        unit_label = extract_unit_label(instrument_id)
        inst = await self._agent.resource(unit_label).get_instrument_info(instrument_id)
        return inst

    async def dump_port_state(self, port_id: ResourceId) -> str:
        """Return a human-readable dump of the worker's shadow state for a port.

        Output is intended for visual inspection only and may change without
        notice. Do not parse programmatically.
        """
        unit_label = extract_unit_label(port_id)
        return await self._agent.diagnostics(unit_label).dump_port_state(port_id)
