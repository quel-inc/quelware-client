import quelware_core.pb.quelware.instrument.v1 as pb_inst
from grpclib.client import Channel
from quelware_core.entities import directives
from quelware_core.entities.clock import CurrentCount, ReferenceCount
from quelware_core.entities.instrument import InstrumentStatus
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.result import FixedTimelineResult
from quelware_core.entities.session import SessionToken
from quelware_core.entities.waveform.sampled import (
    IqWaveform,
    iq_array_from_lists,
)
from quelware_core.pb_converter.directive import directive_to_pb
from quelware_core.pb_converter.instrument import instrument_status_from_pb

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
        resource_id: ResourceId,
    ) -> bool:
        req = pb_inst.SetupRequest(session_token=token, resource_id=resource_id)
        await self._service.setup(req)  # TODO: error handling
        return True

    async def get_clock_snapshot(
        self,
    ) -> tuple[CurrentCount, ReferenceCount]:
        req = pb_inst.GetClockSnapshotRequest()
        resp = await self._service.get_clock_snapshot(req)
        return (resp.current_count, resp.reference_count)

    async def schedule_launch(self, target_time: int) -> bool:
        req = pb_inst.ScheduleLaunchRequest()
        await self._service.schedule_launch(req)  # TODO: error handling
        return True

    async def fetch_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
    ) -> ResultContainer:
        req = pb_inst.FetchResultRequest()
        resp = await self._service.fetch_result(req)  # TODO: error handling

        res = ResultContainer()
        if resp.fixed_timeline_result:
            iq_datas = {}
            for name, waveforms in resp.fixed_timeline_result.iq_data.items():
                if name not in iq_datas:
                    iq_datas[name] = []
                for wf in waveforms.waveforms:
                    if wf.sampled:
                        iq_waveform = IqWaveform(
                            sampling_period_fs=wf.sampled.sampling_period_fs,
                            iq_array=iq_array_from_lists(
                                wf.sampled.i_samples, wf.sampled.q_samples
                            ),
                        )
                        iq_datas[name].append(iq_waveform)
            res.fixed_timeline = FixedTimelineResult(iq_datas=iq_datas)
        return res


__all__ = ["InstrumentAgentGrpc"]
