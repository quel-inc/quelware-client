import pytest
from grpclib.client import Channel

from quelware_client.infra.diagnostics_agent_grpc import DiagnosticsAgentGrpc
from quelware_client.infra.health_agent_grpc import HealthAgentGrpc
from quelware_client.infra.instrument_agent_grpc import InstrumentAgentGrpc
from quelware_client.infra.resource_agent_grpc import ResourceAgentGrpc
from quelware_client.infra.session_agent_grpc import SessionAgentGrpc
from quelware_client.infra.trigger_agent_grpc import TriggerAgentGrpc
from quelware_client.infra.worker_agent_grpc import WorkerAgentGrpc


class _NoAnswer:
    metadata = None

    async def check(self):
        raise TimeoutError("Deadline exceeded")


@pytest.mark.asyncio
async def test_a_unit_that_does_not_answer_fails_its_health_check() -> None:
    agent = HealthAgentGrpc.__new__(HealthAgentGrpc)
    agent._channel = None  # type: ignore[assignment]
    agent._service = _NoAnswer()  # type: ignore[assignment]

    assert await agent.check() is False


@pytest.mark.asyncio
async def test_every_call_has_a_deadline() -> None:
    channel = Channel("localhost", 1)
    try:
        for cls in (
            DiagnosticsAgentGrpc,
            HealthAgentGrpc,
            InstrumentAgentGrpc,
            ResourceAgentGrpc,
            SessionAgentGrpc,
            TriggerAgentGrpc,
            WorkerAgentGrpc,
        ):
            assert cls(channel)._service.timeout is not None, cls.__name__
        assert HealthAgentGrpc(channel)._service.timeout == 10.0
    finally:
        channel.close()
