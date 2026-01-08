from collections.abc import Callable, Sequence
from typing import overload

from quelware_core.entities.directives import Directive, FixedTimelineDirective
from quelware_core.entities.instrument import (
    ConfigVariant,
    FixedTimelineConfig,
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    ProfileVariant,
)
from quelware_core.entities.resource import ResourceId, extract_unit_label
from quelware_core.entities.result import (
    FixedTimelineResult,
    ResultContainer,
    ResultVariant,
    result_extractor_fixed_timeline,
)
from quelware_core.entities.session import SessionToken

from quelware_client.core import Session
from quelware_client.core.interfaces.instrument_agent import InstrumentAgent


class InstrumentDriver[
    D: Directive,
    C: ConfigVariant,
    P: ProfileVariant,
    R: ResultVariant,
]:
    def __init__(  # noqa: PLR0913
        self,
        session_token: SessionToken,
        instrument_id: ResourceId,
        port_id: ResourceId,
        definition: InstrumentDefinition[P],
        config: C,
        instrument_agent: InstrumentAgent,
        result_extractor: Callable[[ResultContainer], R],
    ):
        self._token = session_token
        self._id = instrument_id
        self._port_id = port_id
        self._definition = definition
        self._config = config
        self._agent = instrument_agent
        self._result_extractor = result_extractor

    @overload
    async def apply(self, directive: D) -> bool: ...

    @overload
    async def apply(self, directive: Sequence[D]) -> list[bool]: ...

    async def apply(self, directive) -> bool | list[bool]:
        if isinstance(directive, Sequence):
            results = []
            for d in directive:
                results.append(await self._agent.configure(self._token, self._id, d))
            return results
        else:
            return await self._agent.configure(self._token, self._id, directive)

    @property
    def instrument_config(self) -> C:
        return self._config

    async def setup(self) -> bool:
        return await self._agent.setup(self._token, self._id)

    async def fetch_result(self) -> R:
        res = await self._agent.fetch_result(self._token, self._id)
        return self._result_extractor(res)


type FixedTimelineInstrumentDriver = InstrumentDriver[
    FixedTimelineDirective,
    FixedTimelineConfig,
    FixedTimelineProfile,
    FixedTimelineResult,
]


def create_instrument_driver_fixed_timeline(
    session: Session, instrument_info: InstrumentInfo
) -> FixedTimelineInstrumentDriver:
    if instrument_info.definition.mode is not InstrumentMode.FIXED_TIMELINE:
        raise ValueError(
            f"Instrument mode is mismatched: '{instrument_info.definition.mode}' "
            f"(expected '{InstrumentMode.FIXED_TIMELINE}')"
        )
    if instrument_info.id not in session.available_resource_ids:
        raise ValueError(
            f"instrument '{instrument_info.id}' is not availble in the session "
            f"with token '{session.token}'."
        )

    return InstrumentDriver(
        session.token,
        instrument_info.id,
        instrument_info.port_id,
        instrument_info.definition,
        instrument_info.config,
        session.agent_container.instrument(extract_unit_label(instrument_info.id)),
        result_extractor_fixed_timeline,
    )


__all__ = ["InstrumentDriver"]
