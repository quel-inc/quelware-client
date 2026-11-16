import pytest
import quelware_core.pb.quelware.models.v1 as pb_models
import quelware_core.pb.quelware.worker.v1 as pb_worker
from grpclib import GRPCError
from grpclib.const import Status
from quelware_core.features import known

from quelware_client.core.interfaces.worker_agent import UnitVersion
from quelware_client.infra.worker_agent_grpc import WorkerAgentGrpc

DENSE = known(["dense_waveform"])


class _Worker:
    def __init__(self, answer) -> None:
        self._answer = answer

    async def get_version(self, req):
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


def _agent(answer) -> WorkerAgentGrpc:
    agent = WorkerAgentGrpc.__new__(WorkerAgentGrpc)
    agent._service = _Worker(answer)
    return agent


@pytest.mark.asyncio
async def test_the_version_carries_the_features_the_unit_names() -> None:
    agent = _agent(
        pb_worker.GetVersionResponse(
            info=pb_models.VersionInfo(version="1.0", features=["dense_waveform"])
        )
    )

    assert await agent.get_version() == UnitVersion(version="1.0", features=DENSE)


@pytest.mark.asyncio
async def test_features_this_client_does_not_know_are_left_out() -> None:
    agent = _agent(
        pb_worker.GetVersionResponse(
            info=pb_models.VersionInfo(
                version="2.0", features=["dense_waveform", "from_a_newer_server"]
            )
        )
    )

    version = await agent.get_version()

    assert version is not None
    assert version.features == {"dense_waveform"}


def test_asking_for_an_unknown_feature_raises() -> None:
    version = UnitVersion(version="1.0", features=DENSE)

    assert version.supports("dense_waveform")
    with pytest.raises(ValueError, match="unknown feature"):
        version.supports("dense_wavefrom")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_unit_that_names_no_features_has_none() -> None:
    agent = _agent(
        pb_worker.GetVersionResponse(info=pb_models.VersionInfo(version="0.5.0"))
    )

    assert await agent.get_version() == UnitVersion(version="0.5.0")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [GRPCError(Status.UNIMPLEMENTED), GRPCError(Status.UNAVAILABLE), TimeoutError()],
)
async def test_a_unit_that_does_not_answer_has_no_version(error) -> None:
    agent = _agent(error)

    assert await agent.get_version() is None
