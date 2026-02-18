import asyncio
import logging
from collections.abc import Collection
from types import TracebackType

from quelware_core.entities.instrument import InstrumentDefinition, InstrumentInfo
from quelware_core.entities.resource import (
    ResourceId,
    extract_unit_label,
)
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer

logger = logging.getLogger(__name__)


class Session:
    def __init__(  # noqa: PLR0913
        self,
        resource_ids: Collection[ResourceId],
        agent: AgentContainer,
        ttl_ms: int = 4000,
        tentative_ttl_ms: int = 1000,
        token: SessionToken | None = None,
    ):
        self._rsrc_ids = set(resource_ids)
        self._ttl_ms = ttl_ms
        self._tentative_ttl_ms = tentative_ttl_ms
        self._agent = agent
        self._token = token

    async def open(self):
        token, _ = await self._agent.session.open_session(
            self._rsrc_ids,
            tentative_ttl_ms=self._tentative_ttl_ms,
            committed_ttl_ms=self._ttl_ms,
        )
        self._token = token

    @property
    def available_resource_ids(self) -> set[ResourceId]:
        return self._rsrc_ids.copy()

    @property
    def unit_labels(self) -> list[UnitLabel]:
        return list(set(extract_unit_label(rid) for rid in self._rsrc_ids))

    @property
    def agent_container(self) -> AgentContainer:
        return self._agent

    @property
    def token(self) -> SessionToken:
        if self._token is None:
            raise ValueError("Token not found. Session may not opened.")
        return self._token

    async def close(self):
        await self._agent.session.close_session(self.token)

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
        port_id = ResourceId(port_id)
        unit_label = extract_unit_label(port_id)
        insts = await self._agent.resource(unit_label).deploy_instruments(
            port_id, list(definitions), append=append
        )
        return insts

    async def trigger(self, wait=1000000):
        reference_unit = self.unit_labels[0]
        cur, _ = await self._agent.instrument(reference_unit).get_clock_snapshot()

        target = cur + wait
        unit_to_tasks = {}
        async with asyncio.TaskGroup() as tg:
            for ul in self.unit_labels:
                unit_to_tasks[ul] = tg.create_task(
                    self._agent.instrument(ul).schedule_trigger(
                        self.token, target_time=target
                    )
                )
