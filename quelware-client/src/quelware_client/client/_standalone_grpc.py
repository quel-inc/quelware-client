import logging

from grpclib.client import Channel
from quelware_core.entities.unit import UnitLabel, UnitStatus

from quelware_client.core import AgentContainer, QuelwareClient
from quelware_client.core.interfaces.pat_provider import PatProvider
from quelware_client.infra.diagnostics_agent_grpc import DiagnosticsAgentGrpc
from quelware_client.infra.instrument_agent_grpc import InstrumentAgentGrpc
from quelware_client.infra.pat_provider_file import pat_provider_from_config
from quelware_client.infra.resource_agent_grpc import ResourceAgentGrpc
from quelware_client.infra.trigger_agent_grpc import TriggerAgentGrpc
from quelware_client.infra.worker_agent_grpc import WorkerAgentGrpc
from quelware_client.testing.session_agent_mock import SessionAgentMock
from quelware_client.testing.system_configuration_agent_mock import (
    SystemConfigurationAgentMock,
)

logger = logging.getLogger(__name__)


def create_standalone_client(
    endpoint: str = "localhost",
    port: int = 50051,
    unit_label: str = "mock-unit",
    skip_lock_check: bool = True,
    pat: PatProvider | str | None = None,
) -> QuelwareClient:
    """Create a client that talks directly to a single worker server.

    Intended for testing. The session and system-configuration agents are
    mocked (a single unit, always ACTIVE), while the resource, instrument,
    diagnostics, and worker agents connect over gRPC to ``endpoint:port``. The
    target worker server must be running with lock checking disabled.

    Args:
        endpoint: Host of the worker server.
        port: Port of the worker server.
        unit_label: Label to assign to the single mocked unit.
        skip_lock_check: When True (the default), sessions skip verifying that
            their resources are locked.
        pat: Personal Access Token, as accepted by `create_quelware_client()`.

    Returns:
        A configured, not-yet-started `QuelwareClient`.

    Raises:
        ValueError: If ``pat`` is neither a string, a callable, nor None.
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

    def diagnostics_agent_factory(ul: UnitLabel):
        return DiagnosticsAgentGrpc(
            channel, metadata={"x-unit-label": str(ul), "x-pat": _pat}
        )

    def worker_agent_factory(ul: UnitLabel):
        return WorkerAgentGrpc(channel, metadata={"x-unit-label": str(ul)})

    agent_container = AgentContainer()
    agent_container.session = session_agent
    agent_container.system_configuration = conf_agent
    agent_container.trigger = TriggerAgentGrpc(channel)

    logger.warning("NOTE: Standalone client is for testing purposes.")

    return QuelwareClient(
        agent=agent_container,
        resource_agent_factory=resource_agent_factory,
        instrument_agent_factory=instrument_agent_factory,
        diagnostics_agent_factory=diagnostics_agent_factory,
        worker_agent_factory=worker_agent_factory,
        close_handlers=[channel.close],
        skip_lock_check=skip_lock_check,
    )
