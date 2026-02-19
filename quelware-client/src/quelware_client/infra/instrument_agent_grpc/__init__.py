from collections.abc import Collection

import quelware_core.pb.quelware.instrument.v1 as pb_inst
from grpclib.client import Channel
from quelware_core.entities import directives
from quelware_core.entities.clock import CurrentCount, ReferenceCount
from quelware_core.entities.instrument import InstrumentStatus
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken
from quelware_core.pb_converter.directive import directive_to_pb
from quelware_core.pb_converter.instrument import instrument_status_from_pb
from quelware_core.pb_converter.result import result_container_from_pb

from quelware_client.core.interfaces.instrument_agent import (
    InstrumentAgent,
    ResultContainer,
)


class InstrumentAgentGrpc(InstrumentAgent):
    def __init__(self, grpc_channel: Channel, metadata=None):
        self._channel = grpc_channel
        self._service = pb_inst.InstrumentServiceStub(self._channel, metadata=metadata)

    async def get_status(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> InstrumentStatus:
        req = pb_inst.GetStatusRequest(resource_id=resource_id)
        resp = await self._service.get_status(req)
        return instrument_status_from_pb(resp.status)

    async def configure(
        self,
        token: SessionToken,
        resource_id: ResourceId,
        directive: directives.Directive,
    ) -> bool:
        req = pb_inst.ConfigureRequest(
            session_token=token,
            resource_id=resource_id,
            directive=directive_to_pb(directive),
        )
        await self._service.configure(req)  # TODO: error handling
        return True

    async def setup(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
    ) -> bool:
        req = pb_inst.SetupRequest(session_token=token, resource_ids=list(resource_ids))
        await self._service.setup(req)  # TODO: error handling
        return True

    async def get_clock_snapshot(
        self,
    ) -> tuple[CurrentCount, ReferenceCount]:
        req = pb_inst.GetClockSnapshotRequest()
        resp = await self._service.get_clock_snapshot(req)
        return (resp.current_count, resp.reference_count)

    async def schedule_trigger(self, token: SessionToken, target_time: int) -> bool:
        req = pb_inst.ScheduleTriggerRequest(
            session_token=str(token), clock_count=target_time
        )
        await self._service.schedule_trigger(req)  # TODO: error handling
        return True

    async def fetch_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> ResultContainer:
        req = pb_inst.FetchResultRequest(
            session_token=str(token), resource_id=str(resource_id)
        )
        resp = await self._service.fetch_result(req)

        if resp.result_container:
            return result_container_from_pb(resp.result_container)

        return ResultContainer()


__all__ = ["InstrumentAgentGrpc"]
