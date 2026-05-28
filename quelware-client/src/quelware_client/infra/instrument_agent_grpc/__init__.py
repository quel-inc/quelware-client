from collections.abc import Collection, Sequence

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
from typing_extensions import override

from quelware_client.core.interfaces.instrument_agent import (
    InstrumentAgent,
    ResultContainer,
)
from quelware_client.infra._grpc_retry import call_with_retry


class InstrumentAgentGrpc(InstrumentAgent):
    def __init__(self, grpc_channel: Channel, metadata=None):
        self._channel = grpc_channel
        self._service = pb_inst.InstrumentServiceStub(self._channel, metadata=metadata)

    @override
    async def get_status(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> InstrumentStatus:
        req = pb_inst.GetStatusRequest(resource_id=resource_id)
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(token)
        resp = await call_with_retry(
            lambda: self._service.get_status(req, metadata=metadata), idempotent=True
        )
        return instrument_status_from_pb(resp.status)

    @override
    async def initialize(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
    ) -> None:
        req = pb_inst.InitializeRequest(
            resource_ids=list(resource_ids),
        )
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(token)
        await call_with_retry(lambda: self._service.initialize(req, metadata=metadata))

    @override
    async def configure(
        self,
        token: SessionToken,
        resource_id: ResourceId,
        directives: Sequence[directives.Directive],
    ) -> bool:
        req = pb_inst.ConfigureRequest(
            resource_id=resource_id,
            directives=[directive_to_pb(d) for d in directives],
        )
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(token)
        await call_with_retry(lambda: self._service.configure(req, metadata=metadata))
        return True

    @override
    async def apply(
        self,
        token: SessionToken,
        resource_ids: Collection[ResourceId],
    ) -> bool:
        req = pb_inst.ApplyRequest(resource_ids=list(resource_ids))
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(token)
        await call_with_retry(lambda: self._service.apply(req, metadata=metadata))
        return True

    @override
    async def get_clock_snapshot(
        self,
    ) -> tuple[CurrentCount, ReferenceCount]:
        req = pb_inst.GetClockSnapshotRequest()
        resp = await call_with_retry(
            lambda: self._service.get_clock_snapshot(req), idempotent=True
        )
        return (resp.current_count, resp.reference_count)

    @override
    async def schedule_trigger(
        self,
        token: SessionToken,
        target_time: int,
    ) -> bool:
        req = pb_inst.ScheduleTriggerRequest(
            clock_count=target_time,
        )
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(token)
        await call_with_retry(
            lambda: self._service.schedule_trigger(req, metadata=metadata)
        )
        return True

    @override
    async def trigger_now(
        self,
        token: SessionToken,
    ) -> int:
        req = pb_inst.TriggerNowRequest()
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(token)
        resp = await call_with_retry(
            lambda: self._service.trigger_now(req, metadata=metadata)
        )
        return resp.scheduled_clock_count

    @override
    async def fetch_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> ResultContainer:
        req = pb_inst.FetchResultRequest(resource_id=str(resource_id))
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(token)
        resp = await call_with_retry(
            lambda: self._service.fetch_result(req, metadata=metadata), idempotent=True
        )

        if resp.result_container:
            return result_container_from_pb(resp.result_container)

        return ResultContainer()


__all__ = ["InstrumentAgentGrpc"]
