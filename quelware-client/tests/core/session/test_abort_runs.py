from collections.abc import Collection

import pytest
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer, Session
from quelware_client.core.exceptions import AbortFailedError
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.trigger_agent_mock import TriggerAgentMock
from quelware_client.testing.worker_agent_mock import WorkerAgentMock

_A1 = ResourceId("unit-a:i1")
_A2 = ResourceId("unit-a:i2")
_B1 = ResourceId("unit-b:i1")


class _Agent(InstrumentAgentMock):
    """Records the aborts and fetches that reach the unit, and fails an abort
    when told to."""

    def __init__(self) -> None:
        self.aborted: list[list[ResourceId]] = []
        self.fetched: list[ResourceId] = []
        self.fail_abort = False

    async def abort(
        self, token: SessionToken, resource_ids: Collection[ResourceId]
    ) -> None:
        self.aborted.append(list(resource_ids))
        if self.fail_abort:
            raise RuntimeError("abort refused")

    async def wait_for_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
        timeout_sec: float | None,
    ) -> ResultContainer:
        self.fetched.append(resource_id)
        return ResultContainer()


def _session(a: _Agent, b: _Agent) -> Session:
    agents = AgentContainer()
    agents.trigger = TriggerAgentMock()
    for unit, agent in (("unit-a", a), ("unit-b", b)):
        agents.update_instrument_agent(UnitLabel(unit), agent)
        agents.update_worker_agent(UnitLabel(unit), WorkerAgentMock())
    return Session([_A1, _A2, _B1], agents, token=SessionToken("tok"))


@pytest.mark.asyncio
async def test_each_unit_is_asked_once_with_every_instrument_of_its_run() -> None:
    a, b = _Agent(), _Agent()
    session = _session(a, b)
    await session.trigger([_A1, _A2, _B1])

    await session.abort_runs()

    assert a.aborted == [[_A1, _A2]]
    assert b.aborted == [[_B1]]


@pytest.mark.asyncio
async def test_a_unit_without_a_run_is_not_asked() -> None:
    a, b = _Agent(), _Agent()
    session = _session(a, b)

    await session.abort_runs()
    await session.trigger([_A1])
    await session.abort_runs()

    assert a.aborted == [[_A1]]
    assert b.aborted == []


@pytest.mark.asyncio
async def test_a_unit_that_fails_does_not_keep_the_others_from_being_asked() -> None:
    a, b = _Agent(), _Agent()
    a.fail_abort = True
    session = _session(a, b)
    await session.trigger([_A1, _B1])

    with pytest.raises(AbortFailedError, match="1 of 2 units") as raised:
        await session.abort_runs()

    assert set(raised.value.failures) == {UnitLabel("unit-a")}
    assert b.aborted == [[_B1]]


@pytest.mark.asyncio
async def test_an_aborted_instrument_is_still_waited_for() -> None:
    a = _Agent()
    session = _session(a, _Agent())
    await session.trigger([_A1])

    await session.abort_runs()

    # the unit answers the wait with its abort error
    assert set(await session.wait_for_results([_A1])) == {_A1}
    assert a.fetched == [_A1]
