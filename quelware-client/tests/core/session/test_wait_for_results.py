import asyncio

import pytest
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer, Session
from quelware_client.core.exceptions import RunFailedError
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.trigger_agent_mock import TriggerAgentMock

_OK_A = ResourceId("unit-a:ok")
_OK_B = ResourceId("unit-b:ok")
_FAILS = ResourceId("unit-a:fails")
_HANGS = ResourceId("unit-b:hangs")


class _Agent(InstrumentAgentMock):
    def __init__(self) -> None:
        self.cancelled: list[ResourceId] = []

    async def wait_for_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
        timeout_sec: float | None,
    ) -> ResultContainer:
        if resource_id == _FAILS:
            raise RuntimeError("error on unit SUB0_DAC_A3: past_counter=True")
        if resource_id == _HANGS:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.cancelled.append(resource_id)
                raise
        await asyncio.sleep(0.01)
        return ResultContainer()


async def _triggered(agent: _Agent, ids: list[ResourceId]) -> Session:
    agents = AgentContainer()
    agents.trigger = TriggerAgentMock(scheduled_clock_count=0)
    for unit in ("unit-a", "unit-b"):
        agents.update_instrument_agent(UnitLabel(unit), agent)
    session = Session([_OK_A, _OK_B, _FAILS, _HANGS], agents, token=SessionToken("tok"))
    await session.trigger(ids)
    return session


@pytest.mark.asyncio
async def test_returns_every_instrument_s_result() -> None:
    session = await _triggered(_Agent(), [_OK_A, _OK_B])

    results = await session.wait_for_results([_OK_A, _OK_B])

    assert set(results) == {_OK_A, _OK_B}


@pytest.mark.asyncio
async def test_a_failure_is_reported_after_the_others_complete() -> None:
    ids = [_OK_A, _FAILS, _OK_B]
    session = await _triggered(_Agent(), ids)

    with pytest.raises(RunFailedError, match="past_counter") as raised:
        await session.wait_for_results(ids)

    assert set(raised.value.failures) == {_FAILS}
    assert set(raised.value.results) == {_OK_A, _OK_B}


@pytest.mark.asyncio
async def test_a_timeout_names_the_instruments_still_running() -> None:
    agent = _Agent()
    session = await _triggered(agent, [_OK_A, _HANGS])

    with pytest.raises(TimeoutError, match="hangs"):
        await session.wait_for_results([_OK_A, _HANGS], timeout_sec=0.1)

    assert agent.cancelled == [_HANGS]


@pytest.mark.asyncio
async def test_no_instruments_returns_at_once() -> None:
    session = await _triggered(_Agent(), [])

    assert await session.wait_for_results([]) == {}
