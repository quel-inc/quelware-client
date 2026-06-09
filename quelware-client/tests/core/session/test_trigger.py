import pytest
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer, Session
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.trigger_agent_mock import TriggerAgentMock
from quelware_client.testing.worker_agent_mock import WorkerAgentMock


def _build_agents(
    units: list[UnitLabel], trigger_agent: TriggerAgentMock
) -> AgentContainer:
    agents = AgentContainer()
    agents.trigger = trigger_agent
    for u in units:
        agents.update_instrument_agent(u, InstrumentAgentMock())
        agents.update_worker_agent(u, WorkerAgentMock())
    return agents


@pytest.mark.asyncio
async def test_trigger_goes_through_manager_with_requested_wait_ms():
    trig = TriggerAgentMock(scheduled_clock_count=42_000)
    units = [UnitLabel("unit-a"), UnitLabel("unit-b")]
    agents = _build_agents(units, trig)
    rids = [ResourceId(f"{u}:i1") for u in units]
    session = Session(rids, agents, token=SessionToken("tok"))

    scheduled = await session.trigger(rids, wait_ms=200)

    assert scheduled == 42_000
    assert len(trig.calls) == 1
    token, sent_ids, wait_ms = trig.calls[0]
    assert token == SessionToken("tok")
    assert set(sent_ids) == set(rids)
    assert wait_ms == 200
