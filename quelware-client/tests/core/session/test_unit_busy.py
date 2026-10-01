import asyncio
from collections.abc import Collection

import pytest
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer, Session
from quelware_client.core.exceptions import InitializeFailedError, UnitBusyError
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.trigger_agent_mock import TriggerAgentMock

_A1 = ResourceId("unit-a:i1")
_A2 = ResourceId("unit-a:i2")
_B1 = ResourceId("unit-b:i1")


class _Agent(InstrumentAgentMock):
    """Holds each arm and initialize until released, or fails them."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.fail = False

    async def _hold(self) -> None:
        self.entered.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("unit lost")

    async def arm(
        self, token: SessionToken, resource_ids: Collection[ResourceId]
    ) -> bool:
        await self._hold()
        return True

    async def initialize(
        self, token: SessionToken, resource_ids: Collection[ResourceId]
    ) -> None:
        await self._hold()


def _session(agent: _Agent) -> Session:
    agents = AgentContainer()
    agents.trigger = TriggerAgentMock()
    for unit in ("unit-a", "unit-b"):
        agents.update_instrument_agent(UnitLabel(unit), agent)
    return Session([_A1, _A2, _B1], agents, token=SessionToken("tok"))


async def _under_way(agent: _Agent, coro) -> asyncio.Future:
    """Start a trigger or an initialize, and return once it reaches the unit."""
    task = asyncio.ensure_future(coro)
    await asyncio.wait_for(agent.entered.wait(), timeout=5.0)
    assert not task.done()
    return task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("trigger", "trigger"),
        ("trigger", "initialize"),
        ("initialize", "trigger"),
        ("initialize", "initialize"),
    ],
)
async def test_a_second_one_on_a_unit_under_way_is_refused(first, second) -> None:
    agent = _Agent()
    session = _session(agent)
    under_way = await _under_way(agent, getattr(session, first)([_A1]))

    with pytest.raises(UnitBusyError, match="unit-a"):
        await getattr(session, second)([_A2])

    agent.release.set()
    await under_way


@pytest.mark.asyncio
async def test_other_units_are_not_held() -> None:
    agent = _Agent()
    session = _session(agent)
    under_way = await _under_way(agent, session.trigger([_A1]))
    other = asyncio.ensure_future(session.trigger([_B1]))
    await asyncio.sleep(0)

    agent.release.set()
    await asyncio.gather(under_way, other)

    assert set(await session.wait_for_results([_A1, _B1])) == {_A1, _B1}


@pytest.mark.asyncio
async def test_a_unit_is_let_go_when_its_trigger_fails() -> None:
    agent = _Agent()
    agent.fail = True
    agent.release.set()
    session = _session(agent)

    with pytest.raises(RuntimeError, match="unit lost"):
        await session.trigger([_A1])

    agent.fail = False
    await session.trigger([_A1])
    assert set(await session.wait_for_results([_A1])) == {_A1}


class _Counting(InstrumentAgentMock):
    """Counts the initializes under way at once."""

    def __init__(self) -> None:
        self.under_way = 0
        self.most = 0

    async def initialize(
        self, token: SessionToken, resource_ids: Collection[ResourceId]
    ) -> None:
        self.under_way += 1
        self.most = max(self.most, self.under_way)
        await asyncio.sleep(0.01)
        self.under_way -= 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("parallel", "most"), [(False, 1), (True, 2)])
async def test_units_are_initialized_at_once_unless_not_parallel(
    parallel, most
) -> None:
    agent = _Counting()
    agents = AgentContainer()
    for unit in ("unit-a", "unit-b"):
        agents.update_instrument_agent(UnitLabel(unit), agent)
    session = Session([_A1, _B1], agents, token=SessionToken("tok"))

    await session.initialize([_A1, _B1], parallel=parallel)

    assert agent.most == most


class _UnitAgent(InstrumentAgentMock):
    """One unit's agent: it takes a while to initialize, or fails."""

    def __init__(self, fails: bool, sec: float) -> None:
        self.fails = fails
        self.sec = sec
        self.called = False
        self.finished = False

    async def initialize(
        self, token: SessionToken, resource_ids: Collection[ResourceId]
    ) -> None:
        self.called = True
        await asyncio.sleep(self.sec)
        self.finished = True
        if self.fails:
            raise RuntimeError(f"initialize lost on {resource_ids}")


def _session_of(a: _UnitAgent, b: _UnitAgent) -> Session:
    agents = AgentContainer()
    agents.trigger = TriggerAgentMock()
    agents.update_instrument_agent(UnitLabel("unit-a"), a)
    agents.update_instrument_agent(UnitLabel("unit-b"), b)
    return Session([_A1, _B1], agents, token=SessionToken("tok"))


@pytest.mark.asyncio
async def test_a_failed_unit_is_reported_once_every_unit_has_finished() -> None:
    a, b = _UnitAgent(fails=True, sec=0.0), _UnitAgent(fails=False, sec=0.05)
    session = _session_of(a, b)

    with pytest.raises(InitializeFailedError) as raised:
        await session.initialize([_A1, _B1], parallel=True)

    assert set(raised.value.failures) == {UnitLabel("unit-a")}
    assert b.finished
    # the units are let go only now, so the next trigger is not refused
    await session.trigger([_B1])


@pytest.mark.asyncio
async def test_the_error_of_every_failed_unit_is_kept() -> None:
    a, b = _UnitAgent(fails=True, sec=0.0), _UnitAgent(fails=True, sec=0.01)
    session = _session_of(a, b)

    with pytest.raises(InitializeFailedError, match="2 of 2 units") as raised:
        await session.initialize([_A1, _B1], parallel=True)

    assert set(raised.value.failures) == {UnitLabel("unit-a"), UnitLabel("unit-b")}


@pytest.mark.asyncio
async def test_one_after_another_a_failed_unit_does_not_stop_the_rest() -> None:
    a, b = _UnitAgent(fails=True, sec=0.0), _UnitAgent(fails=False, sec=0.0)
    session = _session_of(a, b)

    with pytest.raises(InitializeFailedError, match="1 of 2 units") as raised:
        await session.initialize([_A1, _B1], parallel=False)

    assert set(raised.value.failures) == {UnitLabel("unit-a")}
    assert b.finished


@pytest.mark.asyncio
async def test_units_are_initialized_at_once_by_default() -> None:
    agent = _Counting()
    agents = AgentContainer()
    for unit in ("unit-a", "unit-b"):
        agents.update_instrument_agent(UnitLabel(unit), agent)
    session = Session([_A1, _B1], agents, token=SessionToken("tok"))

    await session.initialize([_A1, _B1])

    assert agent.most == 2
