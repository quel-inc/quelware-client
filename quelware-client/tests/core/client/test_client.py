import pytest
from quelware_core.entities.resource import (
    ResourceId,
    ResourceInfo,
    ResourceType,
)
from quelware_core.entities.unit import UnitLabel, UnitStatus

from quelware_client.core import AgentContainer, QuelwareClient
from quelware_client.core._session import Session
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.resource_agent_mock import ResourceAgentMock
from quelware_client.testing.system_configuration_agent_mock import (
    SystemConfigurationAgentMock,
)


@pytest.mark.asyncio
async def test_agent_initialization():
    agent = AgentContainer()
    agent.system_configuration = SystemConfigurationAgentMock(
        unit_to_status={
            UnitLabel("unit-a"): UnitStatus.ACTIVE,
            UnitLabel("unit-b"): UnitStatus.ACTIVE,
            UnitLabel("unit-c"): UnitStatus.RELEASED,
        }
    )

    def resource_agent_factory(_):
        return ResourceAgentMock([])

    def instrument_agent_factory(_):
        return InstrumentAgentMock()

    client = QuelwareClient(
        agent=agent,
        resource_agent_factory=resource_agent_factory,
        instrument_agent_factory=instrument_agent_factory,
    )
    await client.initialize()

    # access to the properties without error
    client.agent.resource(UnitLabel("unit-a"))
    client.agent.resource(UnitLabel("unit-b"))
    client.agent.instrument(UnitLabel("unit-a"))
    client.agent.instrument(UnitLabel("unit-b"))


@pytest.mark.asyncio
async def test_list_unit_labels():
    agent = AgentContainer()
    unit_to_status = {
        UnitLabel("unit-a"): UnitStatus.ACTIVE,
        UnitLabel("unit-b"): UnitStatus.ACTIVE,
        UnitLabel("unit-c"): UnitStatus.RELEASED,
    }
    agent.system_configuration = SystemConfigurationAgentMock(
        unit_to_status=unit_to_status
    )
    client = QuelwareClient(agent=agent)
    await client.initialize()
    res = client.list_unit_labels()
    assert set(res) == set(
        ul for ul, s in unit_to_status.items() if s is UnitStatus.ACTIVE
    )


@pytest.mark.asyncio
async def test_list_resources():
    agent = AgentContainer()
    agent.system_configuration = SystemConfigurationAgentMock(
        unit_to_status={
            UnitLabel("unit-a"): UnitStatus.ACTIVE,
            UnitLabel("unit-b"): UnitStatus.ACTIVE,
        }
    )
    agent.update_resource_agent(
        UnitLabel("unit-a"),
        ResourceAgentMock(
            resource_infos=[
                ResourceInfo(id=ResourceId("unit-a:p1"), type=ResourceType.PORT)
            ]
        ),
    )
    agent.update_resource_agent(
        UnitLabel("unit-b"),
        ResourceAgentMock(
            resource_infos=[
                ResourceInfo(id=ResourceId("unit-b:p1"), type=ResourceType.PORT),
                ResourceInfo(id=ResourceId("unit-b:i1"), type=ResourceType.INSTRUMENT),
                ResourceInfo(id=ResourceId("unit-b:i2"), type=ResourceType.INSTRUMENT),
            ]
        ),
    )
    client = QuelwareClient(agent=agent)
    await client.initialize()
    res = await client.list_resource_infos()

    print(res)
    assert len(res) == 1 + 3


@pytest.mark.asyncio
async def test_open_session():
    target_rsrc_ids = [
        ResourceId("unit-c:i1"),
        ResourceId("unit-c:i2"),
        ResourceId("unit-d:i1"),
    ]
    agent = AgentContainer()
    client = QuelwareClient(
        agent=agent,
    )
    ttl_ms = 3000
    session = client.create_session(target_rsrc_ids, ttl_ms)
    assert isinstance(session, Session)


@pytest.mark.asyncio
async def test_get_port():
    unit_label = UnitLabel("unit-a")
    port_id = ResourceId(f"{unit_label}:p1")
    agent = AgentContainer()
    agent.update_resource_agent(
        unit_label,
        ResourceAgentMock([ResourceInfo(id=port_id, type=ResourceType.PORT)]),
    )
    client = QuelwareClient(
        agent=agent,
    )

    await client.get_port_info(port_id)


@pytest.mark.asyncio
async def test_get_instrument():
    unit_label = UnitLabel("unit-a")
    inst_id = ResourceId(f"{unit_label}:i1")
    agent = AgentContainer()
    agent.update_resource_agent(
        unit_label,
        ResourceAgentMock([ResourceInfo(id=inst_id, type=ResourceType.INSTRUMENT)]),
    )
    client = QuelwareClient(
        agent=agent,
    )

    await client.get_instrument_info(inst_id)
