import asyncio
import logging
import math
from collections.abc import Collection
from types import TracebackType
from typing import cast

from quelware_core.entities.instrument import InstrumentDefinition, InstrumentInfo
from quelware_core.entities.resource import (
    ResourceId,
    extract_unit_label,
)
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer
from quelware_client.core.trigger_count_proposer import (
    FixedOffsetTriggerCountProposer,
    TriggerCountProposer,
)

from ._utils import create_unit_to_ids_map

logger = logging.getLogger(__name__)

_default_count_proposer = FixedOffsetTriggerCountProposer(grid_step=32, offset=16)
_CLOCK_FREQUENCY_HZ = 312_000_000


class Session:
    def __init__(  # noqa: PLR0913
        self,
        resource_ids: Collection[ResourceId],
        agent: AgentContainer,
        ttl_ms: int = 4000,
        tentative_ttl_ms: int = 1000,
        token: SessionToken | None = None,
        trigger_count_proposer: TriggerCountProposer | None = None,
    ):
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

    async def open(self):
        token, _ = await self._agent.session.open_session(
            self._rsrc_ids,
            tentative_ttl_ms=self._tentative_ttl_ms,
            committed_ttl_ms=self._ttl_ms,
        )
        self._token = token
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
        return self._rsrc_ids.copy()

    @property
    def unit_labels(self) -> list[UnitLabel]:
        return list(self._unit_to_ids)

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
        logger.info(f"Session closed. session_token={self.token}")

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
            port_id, list(definitions), append, self.token
        )
        return insts

    async def trigger(self, instrument_ids: Collection[ResourceId], wait_ms=100):
        unit_to_ids = create_unit_to_ids_map(instrument_ids)

        logger.info(f"starting application (token= {self.token} )")
        apply_coros = [
            self._agent.instrument(unit_label).apply(self.token, ids)
            for unit_label, ids in unit_to_ids.items()
        ]
        await asyncio.gather(*apply_coros)
        logger.info(f"finished application (token= {self.token} )")

        reference_unit = extract_unit_label(next(iter(instrument_ids)))
        cur, ref = await self._agent.instrument(reference_unit).get_clock_snapshot()
        wait_count = math.ceil(wait_ms * _CLOCK_FREQUENCY_HZ / 1000)
        target_time = self._trigger_count_proposer.propose_count(cur, ref, wait_count)

        trigger_coros = [
            self._agent.instrument(unit_label).schedule_trigger(self.token, target_time)
            for unit_label, ids in unit_to_ids.items()
        ]
        await asyncio.gather(*trigger_coros)
