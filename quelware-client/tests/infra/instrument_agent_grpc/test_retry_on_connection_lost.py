import pytest
import quelware_core.pb.quelware.instrument.v1 as pb_inst
from grpclib.exceptions import StreamTerminatedError
from quelware_core.entities.directives import SetFrequency
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken

from quelware_client.infra.instrument_agent_grpc import InstrumentAgentGrpc

TOKEN = SessionToken("t")
RID = ResourceId("unit-a:r1")


class _LosesTheFirstCall:
    """Stands in for the stub: the first call of each method loses its connection."""

    metadata = None

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def __getattr__(self, name: str):
        async def call(req, metadata=None):
            self.calls[name] = self.calls.get(name, 0) + 1
            if self.calls[name] == 1:
                raise StreamTerminatedError("Connection lost")
            if name == "trigger_now":
                return pb_inst.TriggerNowResponse(scheduled_clock_count=42)
            return None

        return call


def _agent() -> tuple[InstrumentAgentGrpc, _LosesTheFirstCall]:
    agent = InstrumentAgentGrpc.__new__(InstrumentAgentGrpc)
    service = _LosesTheFirstCall()
    agent._service = service  # type: ignore[assignment]
    return agent, service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("initialize", lambda a: a.initialize(TOKEN, [RID])),
        ("configure", lambda a: a.configure(TOKEN, RID, [SetFrequency(hz=5e9)])),
        ("apply", lambda a: a.arm(TOKEN, [RID])),
        ("trigger_now", lambda a: a.trigger_now(TOKEN, None)),
    ],
)
async def test_a_call_that_can_be_made_again_is_retried_on_a_lost_connection(
    method, call
) -> None:
    agent, service = _agent()

    await call(agent)

    assert service.calls == {method: 2}


@pytest.mark.asyncio
async def test_a_scheduled_trigger_is_not_retried_on_a_lost_connection() -> None:
    agent, service = _agent()

    with pytest.raises(StreamTerminatedError):
        await agent.schedule_trigger(TOKEN, 1000)

    assert service.calls == {"schedule_trigger": 1}
