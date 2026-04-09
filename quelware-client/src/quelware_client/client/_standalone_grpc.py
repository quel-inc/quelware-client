import logging

from grpclib.client import Channel
from quelware_core.entities.unit import UnitLabel, UnitStatus

from quelware_client.core import AgentContainer, QuelwareClient
from quelware_client.core.interfaces.pat_provider import PatProvider
from quelware_client.infra.instrument_agent_grpc import InstrumentAgentGrpc
from quelware_client.infra.pat_provider_file import pat_provider_from_config
from quelware_client.infra.resource_agent_grpc import ResourceAgentGrpc
from quelware_client.testing.session_agent_mock import SessionAgentMock
from quelware_client.testing.system_configuration_agent_mock import (
    SystemConfigurationAgentMock,
)

logger = logging.getLogger(__name__)


def create_standalone_client(
    endpoint: str = "localhost",
    port: int = 50051,
    unit_label: str = "mock-unit",
    skip_lock_check=True,
    pat: PatProvider | str | None = None,
):
    """Create a standalone client.

    Note that the target worker server must be running with lock checking
    disabled to use this client.
    """
    channel = Channel(endpoint, port)
    target_unit = UnitLabel(unit_label)

    if pat is None:
        _pat = pat_provider_from_config()
    elif isinstance(pat, str):
        _pat = pat
    elif callable(pat):
        _pat = pat()
    else:
        raise ValueError(f"Unknown type for pat: {pat}")

    conf_agent = SystemConfigurationAgentMock({target_unit: UnitStatus.ACTIVE})
    session_agent = SessionAgentMock()

    def resource_agent_factory(ul: UnitLabel):
        return ResourceAgentGrpc(
            channel, metadata={"x-unit-label": str(ul), "x-pat": _pat}
        )

    def instrument_agent_factory(ul: UnitLabel):
        return InstrumentAgentGrpc(
            channel, metadata={"x-unit-label": str(ul), "x-pat": _pat}
        )

    agent_container = AgentContainer()
    agent_container.session = session_agent
    agent_container.system_configuration = conf_agent

    logger.warning("NOTE: Standalone client is for testing purposes.")

    return QuelwareClient(
        agent=agent_container,
        resource_agent_factory=resource_agent_factory,
        instrument_agent_factory=instrument_agent_factory,
        close_handlers=[channel.close],
        skip_lock_check=skip_lock_check,
    )
