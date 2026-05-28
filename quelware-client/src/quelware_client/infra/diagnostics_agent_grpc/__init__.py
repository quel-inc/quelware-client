import quelware_core.pb.quelware.diagnostics.v1 as pb_diag
from grpclib.client import Channel
from quelware_core.entities.resource import ResourceId

from quelware_client.core.interfaces.diagnostics_agent import DiagnosticsAgent
from quelware_client.infra._grpc_retry import call_with_retry


class DiagnosticsAgentGrpc(DiagnosticsAgent):
    def __init__(self, grpc_channel: Channel, metadata=None):
        self._channel = grpc_channel
        self._service = pb_diag.DiagnosticsServiceStub(self._channel, metadata=metadata)

    async def dump_port_state(self, port_id: ResourceId) -> str:
        req = pb_diag.DumpPortStateRequest(port_id=str(port_id))
        resp = await call_with_retry(
            lambda: self._service.dump_port_state(req), idempotent=True
        )
        return resp.text


__all__ = ["DiagnosticsAgentGrpc"]
