from contextlib import asynccontextmanager

from quelware_core.entities.resource import ResourceInfo
from quelware_core.entities.unit import UnitLabel, UnitStatus

from quelware_client.core import AgentContainer, QuelwareClient
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.resource_agent_mock import ResourceAgentMock
from quelware_client.testing.session_agent_mock import SessionAgentMock
from quelware_client.testing.system_configuration_agent_mock import (
    SystemConfigurationAgentMock,
)


@asynccontextmanager
async def create_mock_quelware_client(
    unit_to_status: dict[UnitLabel, UnitStatus],
    unit_to_resources: dict[UnitLabel, list[ResourceInfo]],
):
    agent_container = AgentContainer()

    agent_container.system_configuration = SystemConfigurationAgentMock(unit_to_status)

    agent_container.session = SessionAgentMock()

    def resource_agent_factory(ul: UnitLabel) -> ResourceAgentMock:
        rinfos = unit_to_resources.get(ul, [])
        return ResourceAgentMock(rinfos)

    def instrument_agent_factory(ul: UnitLabel) -> InstrumentAgentMock:
        return InstrumentAgentMock()

    client = QuelwareClient(
        agent=agent_container,
        resource_agent_factory=resource_agent_factory,
        instrument_agent_factory=instrument_agent_factory,
    )

    await client.initialize()

    try:
        yield client
    finally:
        pass
