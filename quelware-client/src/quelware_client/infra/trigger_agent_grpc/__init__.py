from collections.abc import Collection

import quelware_core.pb.quelware.trigger.v1 as pb_trigger
from betterproto2.grpclib.grpclib_client import MetadataLike
from grpclib import GRPCError
from grpclib.client import Channel
from grpclib.const import Status
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken

from quelware_client.core.exceptions import ServiceUnavailableError
from quelware_client.core.interfaces.trigger_agent import TriggerAgent
from quelware_client.infra._grpc_retry import call_with_retry


class TriggerAgentGrpc(TriggerAgent):
    def __init__(self, grpc_channel: Channel, metadata: MetadataLike | None = None):
        self._channel = grpc_channel
        self._service = pb_trigger.TriggerServiceStub(self._channel, metadata=metadata)

    async def trigger(
        self,
        token: SessionToken,
        instrument_ids: Collection[ResourceId],
        requested_min_wait_ms: int | None,
    ) -> int:
        req = pb_trigger.TriggerRequest(
            instrument_ids=[str(r) for r in instrument_ids],
            requested_min_wait_ms=requested_min_wait_ms,
        )
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(token)
        try:
            resp = await call_with_retry(
                lambda: self._service.trigger(req, metadata=metadata)
            )
        except GRPCError as e:
            if e.status is Status.UNIMPLEMENTED:
                raise ServiceUnavailableError(
                    f"TriggerService is not available: {e.message}"
                ) from e
            # Some gRPC proxies surface upstream missing-route as UNKNOWN + content-type
            # error.
            if e.status is Status.UNKNOWN and e.message and "content-type" in e.message:
                raise ServiceUnavailableError(
                    f"TriggerService route not reachable via proxy: {e.message}"
                ) from e
            raise
        return resp.scheduled_clock_count


__all__ = ["TriggerAgentGrpc"]
