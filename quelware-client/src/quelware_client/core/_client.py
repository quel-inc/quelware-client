import asyncio
from collections.abc import Callable, Collection
from typing import cast

from quelware_core.entities.instrument import InstrumentInfo
from quelware_core.entities.port import PortInfo
from quelware_core.entities.resource import (
    ResourceId,
    ResourceInfo,
    extract_unit_label,
)
from quelware_core.entities.unit import UnitLabel

from quelware_client.core._agent_container import AgentContainer
from quelware_client.core.interfaces.instrument_agent import InstrumentAgent

from ._session import Session
from .interfaces.resource_agent import ResourceAgent

type AgentFactory[A] = Callable[[UnitLabel], A]

type _ResourceId = ResourceId | str


class QuelwareClient:
    def __init__(
        self,
        agent: AgentContainer,
        resource_agent_factory: AgentFactory[ResourceAgent] | None = None,
        instrument_agent_factory: AgentFactory[InstrumentAgent] | None = None,
    ):
        self._agent = agent
        self._rsrc_agent_factory = resource_agent_factory
        self._inst_agent_factory = instrument_agent_factory
        self._unit_labels: list[UnitLabel] = []

    @property
    def agent(self) -> AgentContainer:
        return self._agent

    async def initialize(self):
        self._unit_labels = await self._agent.system_configuration.list_active_units()
        for ul in self._unit_labels:
            if self._rsrc_agent_factory:
                self._agent.update_resource_agent(ul, self._rsrc_agent_factory(ul))
            if self._inst_agent_factory:
                self._agent.update_instrument_agent(ul, self._inst_agent_factory(ul))

    def list_unit_labels(self) -> list[UnitLabel]:
        return list(self._unit_labels)

    def create_session(
        self,
        resource_ids: Collection[_ResourceId],
        ttl_ms: int = 4000,
        tentative_ttl_ms: int = 1000,
    ) -> Session:
        return Session(
            resource_ids=cast(list[ResourceId], resource_ids),
            agent=self._agent,
            ttl_ms=ttl_ms,
            tentative_ttl_ms=tentative_ttl_ms,
        )

    async def list_resource_infos(self) -> list[ResourceInfo]:
        tasks = []
        async with asyncio.TaskGroup() as tg:
            for inst_agent in (self._agent.resource(ul) for ul in self._unit_labels):
                tasks.append(tg.create_task(inst_agent.list_resource_infos()))
        rsrc_infos: list[ResourceInfo] = []
        for t in tasks:
            rsrc_infos.extend(t.result())
        return rsrc_infos

    async def get_port_info(self, port_id: ResourceId) -> PortInfo:
        unit_label = extract_unit_label(port_id)
        port = await self._agent.resource(unit_label).get_port_info(port_id)
        return port

    async def get_instrument_info(self, instrument_id: ResourceId) -> InstrumentInfo:
        unit_label = extract_unit_label(instrument_id)
        inst = await self._agent.resource(unit_label).get_instrument_info(instrument_id)
        return inst
