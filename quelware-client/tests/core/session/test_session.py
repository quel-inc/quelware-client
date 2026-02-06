from unittest.mock import AsyncMock

import pytest
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import (
    ResourceCategory,
    ResourceId,
    ResourceInfo,
)
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer, Session
from quelware_client.testing.resource_agent_mock import ResourceAgentMock
from quelware_client.testing.session_agent_mock import SessionAgentMock


@pytest.mark.asyncio
async def test_open_and_close():
    resource_ids = [
        ResourceId("unit-c:i1"),
        ResourceId("unit-c:i2"),
        ResourceId("unit-d:i1"),
    ]
    agent = AgentContainer()
    session_agent_mock = SessionAgentMock()
    session_agent_mock.open_session_result = (SessionToken("token1"), resource_ids)
    session_agent_mock.close_session = AsyncMock()  # type: ignore
    session_agent_mock.close_session.return_value = True  # type: ignore
    agent.session = session_agent_mock
    session = Session(resource_ids, agent, ttl_ms=1234, tentative_ttl_ms=56)

    await session.open()
    await session.close()
    session_agent_mock.close_session.assert_called_once()  # type: ignore


@pytest.mark.asyncio
async def test_open_and_close_with_context():
    resource_ids = [
        ResourceId("unit-c:i1"),
        ResourceId("unit-c:i2"),
        ResourceId("unit-d:i1"),
    ]
    agent = AgentContainer()
    session_agent_mock = SessionAgentMock()
    session_agent_mock.open_session_result = (SessionToken("token1"), resource_ids)
    session_agent_mock.close_session = AsyncMock()  # type: ignore
    session_agent_mock.close_session.return_value = True  # type: ignore
    agent.session = session_agent_mock
    async with Session(
        resource_ids, agent, ttl_ms=1234, tentative_ttl_ms=56
    ) as session:
        assert session.token is not None
    session_agent_mock.close_session.assert_called_once()  # type: ignore


@pytest.mark.asyncio
async def test_configure_instruments():
    unit_label = UnitLabel("unit-a")
    port_id = ResourceId(f"{unit_label}:p1")
    agent = AgentContainer()
    agent.update_resource_agent(
        unit_label,
        ResourceAgentMock([ResourceInfo(id=port_id, category=ResourceCategory.PORT)]),
    )
    session = Session(
        [port_id], agent, ttl_ms=1234, tentative_ttl_ms=56, token=SessionToken("token")
    )

    definitions = [
        InstrumentDefinition(
            alias="inst1",
            mode=InstrumentMode.FIXED_TIMELINE,
            role=InstrumentRole.TRANSCEIVER,
            profile=FixedTimelineProfile(
                frequency_range_min=1000000, frequency_range_max=10000000
            ),
        )
    ]

    res = await session.deploy_instruments(port_id, definitions=definitions)

    assert len(res) == len(definitions)
