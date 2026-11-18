import pytest
import quelware_core.pb.quelware.session.v1 as pb_session
from quelware_core.entities.resource import ResourceId

from quelware_client.infra._timeouts import CALL_TIMEOUT_SEC
from quelware_client.infra.session_agent_grpc import SessionAgentGrpc


class _Sessions:
    def __init__(self) -> None:
        self.calls: list[tuple[pb_session.OpenSessionRequest, float | None]] = []

    async def open_session(self, req, *, timeout=None):
        self.calls.append((req, timeout))
        return pb_session.OpenSessionResponse(token="t", resource_ids=["u:p"])


def _agent() -> tuple[SessionAgentGrpc, _Sessions]:
    agent = SessionAgentGrpc.__new__(SessionAgentGrpc)
    service = _Sessions()
    agent._service = service
    return agent, service


@pytest.mark.asyncio
async def test_the_retry_window_is_sent_and_lengthens_the_call_timeout() -> None:
    agent, service = _agent()

    await agent.open_session([ResourceId("u:p")], 1000, 4000, retry_window_ms=20_000)

    ((req, timeout),) = service.calls
    assert req.retry_window_ms == 20_000
    assert timeout == pytest.approx(20 + CALL_TIMEOUT_SEC)


@pytest.mark.asyncio
async def test_no_retry_window_keeps_the_usual_call_timeout() -> None:
    agent, service = _agent()

    await agent.open_session([ResourceId("u:p")], 1000, 4000)

    ((req, timeout),) = service.calls
    assert req.retry_window_ms == 0
    assert timeout == pytest.approx(CALL_TIMEOUT_SEC)
