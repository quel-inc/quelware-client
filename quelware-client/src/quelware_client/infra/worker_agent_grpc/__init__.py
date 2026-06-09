import quelware_core.pb.quelware.worker.v1 as pb_worker
from grpclib.client import Channel
from quelware_core.entities.clock import CurrentCount, ReferenceCount
from typing_extensions import override

from quelware_client.core.interfaces.worker_agent import WorkerAgent
from quelware_client.infra._grpc_retry import call_with_retry


class WorkerAgentGrpc(WorkerAgent):
    def __init__(self, grpc_channel: Channel, metadata=None):
        self._channel = grpc_channel
        self._service = pb_worker.WorkerServiceStub(self._channel, metadata=metadata)

    @override
    async def get_clock_snapshot(self) -> tuple[CurrentCount, ReferenceCount]:
        req = pb_worker.GetClockSnapshotRequest()
        resp = await call_with_retry(
            lambda: self._service.get_clock_snapshot(req), idempotent=True
        )
        return (resp.current_count, resp.reference_count)


__all__ = ["WorkerAgentGrpc"]
