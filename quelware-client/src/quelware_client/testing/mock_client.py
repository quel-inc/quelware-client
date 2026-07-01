from quelware_core.entities.resource import ResourceInfo
from quelware_core.entities.unit import UnitLabel, UnitStatus

from quelware_client.core import AgentContainer, QuelwareClient
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.resource_agent_mock import ResourceAgentMock
from quelware_client.testing.session_agent_mock import SessionAgentMock
from quelware_client.testing.system_configuration_agent_mock import (
    SystemConfigurationAgentMock,
)
from quelware_client.testing.trigger_agent_mock import TriggerAgentMock
from quelware_client.testing.worker_agent_mock import WorkerAgentMock


def create_mock_quelware_client(
    unit_to_status: dict[UnitLabel, UnitStatus],
    unit_to_resources: dict[UnitLabel, list[ResourceInfo]],
) -> QuelwareClient:
    """Create a fully mocked client for tests, requiring no server.

    All agents are in-memory mocks, so the client can be exercised without a
    running QuEL system.

    Args:
        unit_to_status: Status to report for each unit.
        unit_to_resources: Resource information to expose for each unit.

    Returns:
        A configured, not-yet-started `QuelwareClient` backed by mocks.
    """
    agent_container = AgentContainer()

    agent_container.system_configuration = SystemConfigurationAgentMock(unit_to_status)

    agent_container.session = SessionAgentMock()
    agent_container.trigger = TriggerAgentMock()

    def resource_agent_factory(ul: UnitLabel) -> ResourceAgentMock:
        rinfos = unit_to_resources.get(ul, [])
        return ResourceAgentMock(rinfos)

    def instrument_agent_factory(ul: UnitLabel) -> InstrumentAgentMock:
        return InstrumentAgentMock()

    def worker_agent_factory(ul: UnitLabel) -> WorkerAgentMock:
        return WorkerAgentMock()

    return QuelwareClient(
        agent=agent_container,
        resource_agent_factory=resource_agent_factory,
        instrument_agent_factory=instrument_agent_factory,
        worker_agent_factory=worker_agent_factory,
    )
