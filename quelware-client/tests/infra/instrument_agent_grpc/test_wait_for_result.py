import asyncio

import pytest
from grpclib import GRPCError
from grpclib.const import Status
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.session import SessionToken

from quelware_client.infra.instrument_agent_grpc import InstrumentAgentGrpc


class _FakeAgent(InstrumentAgentGrpc):
    """Override fetch_result without needing a real gRPC channel."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    async def fetch_result(self, token, resource_id):
        await asyncio.sleep(0.005)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


TOKEN = SessionToken("t")
RID = ResourceId("unit-a:r1")


@pytest.mark.asyncio
async def test_returns_after_retrying_deadline_exceeded():
    expected = ResultContainer()
    agent = _FakeAgent(
        [
            GRPCError(Status.DEADLINE_EXCEEDED),
            GRPCError(Status.DEADLINE_EXCEEDED),
            expected,
        ]
    )
    got = await agent.wait_for_result(TOKEN, RID, timeout_sec=5.0)
    assert got is expected
    assert agent._outcomes == []


@pytest.mark.asyncio
async def test_propagates_non_deadline_grpc_error():
    agent = _FakeAgent([GRPCError(Status.FAILED_PRECONDITION, "not ready")])
    with pytest.raises(GRPCError) as info:
        await agent.wait_for_result(TOKEN, RID, timeout_sec=5.0)
    assert info.value.status is Status.FAILED_PRECONDITION


@pytest.mark.asyncio
async def test_raises_when_total_timeout_elapses():
    class _AlwaysDeadlineExceeded(_FakeAgent):
        async def fetch_result(self, token, resource_id):
            await asyncio.sleep(0.005)
            raise GRPCError(Status.DEADLINE_EXCEEDED)

    agent = _AlwaysDeadlineExceeded([])
    with pytest.raises(asyncio.TimeoutError):
        await agent.wait_for_result(TOKEN, RID, timeout_sec=0.05)
