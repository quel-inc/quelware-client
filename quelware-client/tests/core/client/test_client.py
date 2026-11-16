import asyncio

import pytest
from quelware_core.entities.resource import (
    ResourceCategory,
    ResourceId,
    ResourceInfo,
)
from quelware_core.entities.unit import UnitLabel, UnitStatus
from quelware_core.features import known

from quelware_client.core import AgentContainer, QuelwareClient
from quelware_client.core._session import Session
from quelware_client.core.interfaces.worker_agent import UnitVersion
from quelware_client.core.unit_control import UnitConfiguration, UnitControlSpec
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.resource_agent_mock import ResourceAgentMock
from quelware_client.testing.system_configuration_agent_mock import (
    SystemConfigurationAgentMock,
)
from quelware_client.testing.worker_agent_mock import WorkerAgentMock

DENSE = known(["dense_waveform"])


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
    expected = unit_to_status.keys()
    assert set(res) == expected


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
                ResourceInfo(id=ResourceId("unit-a:p1"), category=ResourceCategory.PORT)
            ]
        ),
    )
    agent.update_resource_agent(
        UnitLabel("unit-b"),
        ResourceAgentMock(
            resource_infos=[
                ResourceInfo(
                    id=ResourceId("unit-b:p1"), category=ResourceCategory.PORT
                ),
                ResourceInfo(
                    id=ResourceId("unit-b:i1"), category=ResourceCategory.INSTRUMENT
                ),
                ResourceInfo(
                    id=ResourceId("unit-b:i2"), category=ResourceCategory.INSTRUMENT
                ),
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
        ResourceAgentMock([ResourceInfo(id=port_id, category=ResourceCategory.PORT)]),
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
        ResourceAgentMock(
            [ResourceInfo(id=inst_id, category=ResourceCategory.INSTRUMENT)]
        ),
    )
    client = QuelwareClient(
        agent=agent,
    )

    await client.get_instrument_info(inst_id)


@pytest.mark.asyncio
async def test_get_unit_configuration():
    unit_label = UnitLabel("unit-a")
    config = UnitConfiguration(
        supported=(
            UnitControlSpec(key="x.y", allowed_values=("a", "b"), current_value="a"),
        )
    )
    agent = AgentContainer()
    agent.update_worker_agent(unit_label, WorkerAgentMock(unit_configuration=config))
    client = QuelwareClient(agent=agent)

    result = await client.get_unit_configuration(unit_label)

    assert result == config
    assert result.values() == {"x.y": "a"}


@pytest.mark.asyncio
async def test_initialize_reads_each_units_version_and_takes_a_silent_one_as_old():
    agent = AgentContainer()
    agent.system_configuration = SystemConfigurationAgentMock(
        unit_to_status={
            UnitLabel("unit-a"): UnitStatus.ACTIVE,
            UnitLabel("unit-b"): UnitStatus.ACTIVE,
        }
    )
    new = UnitVersion(version="1.0", features=DENSE)
    workers = {
        UnitLabel("unit-a"): WorkerAgentMock(version=new),
        UnitLabel("unit-b"): WorkerAgentMock(version=None),
    }
    client = QuelwareClient(agent=agent, worker_agent_factory=workers.__getitem__)

    await client.initialize()

    assert client.agent.unit_version(UnitLabel("unit-a")) == new
    assert client.agent.unit_version(UnitLabel("unit-b")) is None


@pytest.mark.asyncio
async def test_the_versions_of_many_units_are_read_at_once():
    units = [UnitLabel(f"unit-{i}") for i in range(200)]
    agent = AgentContainer()
    agent.system_configuration = SystemConfigurationAgentMock(
        unit_to_status=dict.fromkeys(units, UnitStatus.ACTIVE)
    )
    asking: set[UnitLabel] = set()
    everyone = asyncio.Event()

    class _AnswersOnceAllAsk(WorkerAgentMock):
        def __init__(self, ul: UnitLabel):
            super().__init__(version=UnitVersion(version="1.0"))
            self._ul = ul

        async def get_version(self) -> UnitVersion | None:
            asking.add(self._ul)
            if len(asking) == len(units):
                everyone.set()
            # read one after another, the first unit would wait here alone
            await asyncio.wait_for(everyone.wait(), timeout=1.0)
            return await super().get_version()

    client = QuelwareClient(agent=agent, worker_agent_factory=_AnswersOnceAllAsk)

    await client.initialize()

    assert all(agent.unit_version(ul) is not None for ul in units)


@pytest.mark.asyncio
async def test_an_instrument_agent_is_built_once_its_units_version_is_read():
    agent = AgentContainer()
    agent.system_configuration = SystemConfigurationAgentMock(
        unit_to_status={UnitLabel("unit-a"): UnitStatus.ACTIVE}
    )
    new = UnitVersion(version="1.0", features=DENSE)
    seen: list[UnitVersion | None] = []

    def instrument_agent_factory(ul: UnitLabel) -> InstrumentAgentMock:
        seen.append(agent.unit_version(ul))
        return InstrumentAgentMock()

    client = QuelwareClient(
        agent=agent,
        instrument_agent_factory=instrument_agent_factory,
        worker_agent_factory=lambda _: WorkerAgentMock(version=new),
    )

    await client.initialize()

    assert seen == [new]
