from contextlib import asynccontextmanager

from grpclib.client import Channel
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer, AgentFactory, QuelwareClient
from quelware_client.core.interfaces.instrument_agent import InstrumentAgent
from quelware_client.core.interfaces.resource_agent import ResourceAgent
from quelware_client.core.interfaces.session_agent import SessionAgent
from quelware_client.core.interfaces.system_configuration_agent import (
    SystemConfigurationAgent,
)
from quelware_client.infra.instrument_agent_grpc import InstrumentAgentGrpc
from quelware_client.infra.resource_agent_grpc import (
    ResourceAgentGrpc,
)
from quelware_client.infra.session_agent_grpc import SessionAgentGrpc
from quelware_client.infra.system_configuration_agent_grpc import (
    SystemConfigurationAgentGrpc,
)


def _create_default_resource_agent_factory(channel):
    def _default_resource_agent_factory(ul: UnitLabel):
        return ResourceAgentGrpc(channel, metadata={"x-unit-label": str(ul)})

    return _default_resource_agent_factory


def _create_default_instrument_agent_factory(channel):
    def _default_command_agent_factory(ul: UnitLabel):
        return InstrumentAgentGrpc(channel, metadata={"x-unit-label": str(ul)})

    return _default_command_agent_factory


@asynccontextmanager
async def create_quelware_client(  # noqa: PLR0913
    endpoint: str = "localhost",
    port: int = 50051,
    session_agent: SessionAgent | None = None,
    configuration_agent: SystemConfigurationAgent | None = None,
    resource_agent_factory: AgentFactory[ResourceAgent] | None = None,
    instrument_agent_factory: AgentFactory[InstrumentAgent] | None = None,
):
    channel = Channel(endpoint, port)

    if resource_agent_factory is None:
        resource_agent_factory = _create_default_resource_agent_factory(channel)

    if instrument_agent_factory is None:
        instrument_agent_factory = _create_default_instrument_agent_factory(channel)

    try:
        agent_container = AgentContainer()
        if session_agent is None:
            agent_container.session = SessionAgentGrpc(channel)
        if configuration_agent is None:
            agent_container.system_configuration = SystemConfigurationAgentGrpc(channel)
        client = QuelwareClient(
            agent=agent_container,
            resource_agent_factory=resource_agent_factory,
            instrument_agent_factory=instrument_agent_factory,
        )
        await client.initialize()
        yield client
    finally:
        channel.close()
