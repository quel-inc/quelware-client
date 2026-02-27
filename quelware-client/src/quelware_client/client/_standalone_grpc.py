from grpclib.client import Channel
from quelware_core.entities.unit import UnitLabel, UnitStatus

from quelware_client.core import AgentContainer, QuelwareClient
from quelware_client.infra.instrument_agent_grpc import InstrumentAgentGrpc
from quelware_client.infra.resource_agent_grpc import ResourceAgentGrpc
from quelware_client.testing.session_agent_mock import SessionAgentMock
from quelware_client.testing.system_configuration_agent_mock import (
    SystemConfigurationAgentMock,
)


def create_standalone_client(
    endpoint: str = "localhost", port: int = 50051, unit_label: str = "mock-unit"
):
    """Create a standalone client.

    Note that the target worker server must be running with lock checking
    disabled to use this client.
    """
    channel = Channel(endpoint, port)
    target_unit = UnitLabel(unit_label)

    conf_agent = SystemConfigurationAgentMock({target_unit: UnitStatus.ACTIVE})
    session_agent = SessionAgentMock()

    def resource_agent_factory(ul: UnitLabel):
        return ResourceAgentGrpc(channel, metadata={"x-unit-label": str(ul)})

    def instrument_agent_factory(ul: UnitLabel):
        return InstrumentAgentGrpc(channel, metadata={"x-unit-label": str(ul)})

    agent_container = AgentContainer()
    agent_container.session = session_agent
    agent_container.system_configuration = conf_agent

    return QuelwareClient(
        agent=agent_container,
        resource_agent_factory=resource_agent_factory,
        instrument_agent_factory=instrument_agent_factory,
        close_handlers=[channel.close],
    )
