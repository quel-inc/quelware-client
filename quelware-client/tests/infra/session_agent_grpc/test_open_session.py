import pytest
import quelware_core.pb.quelware.session.v1 as pb_session
from grpclib.const import Status
from grpclib.exceptions import GRPCError
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.unit import UnitLabel
from quelware_core.grpc_helper.error import build_details

from quelware_client.core.exceptions import QuelwareClientError, UnitUnreachableError
from quelware_client.infra._timeouts import CALL_TIMEOUT_SEC
from quelware_client.infra.session_agent_grpc import SessionAgentGrpc


class _Sessions:
    def __init__(self, error: GRPCError | None = None) -> None:
        self.calls: list[tuple[pb_session.OpenSessionRequest, float | None]] = []
        self._error = error

    async def open_session(self, req, *, timeout=None):
        self.calls.append((req, timeout))
        if self._error is not None:
            raise self._error
        return pb_session.OpenSessionResponse(token="t", resource_ids=["u:p"])


def _agent(error: GRPCError | None = None) -> tuple[SessionAgentGrpc, _Sessions]:
    agent = SessionAgentGrpc.__new__(SessionAgentGrpc)
    service = _Sessions(error)
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


@pytest.mark.asyncio
async def test_an_unreachable_unit_is_named_in_the_error() -> None:
    details = build_details({"unit_labels": ["u"]})
    agent, _ = _agent(GRPCError(Status.UNAVAILABLE, "no answer", details))

    with pytest.raises(UnitUnreachableError) as raised:
        await agent.open_session([ResourceId("u:p")], 1000, 4000)

    assert raised.value.unit_labels == [UnitLabel("u")]


@pytest.mark.asyncio
async def test_an_unavailable_server_that_names_no_unit_is_a_plain_error() -> None:
    agent, _ = _agent(GRPCError(Status.UNAVAILABLE, "no answer"))

    with pytest.raises(QuelwareClientError) as raised:
        await agent.open_session([ResourceId("u:p")], 1000, 4000)

    assert not isinstance(raised.value, UnitUnreachableError)
