from collections.abc import Collection

import quelware_core.pb.quelware.resource.v1 as pb_res
from grpclib.client import Channel
from quelware_core.entities.instrument import (
    InstrumentDefinition,
    InstrumentInfo,
)
from quelware_core.entities.port import PortInfo
from quelware_core.entities.resource import ResourceId, ResourceInfo
from quelware_core.entities.session import SessionToken
from quelware_core.pb_converter.instrument import (
    instrument_definition_to_pb,
    instrument_from_pb,
)
from quelware_core.pb_converter.port import port_role_from_pb
from quelware_core.pb_converter.resource import resource_info_from_pb

from quelware_client.core.interfaces.resource_agent import ResourceAgent


class ResourceAgentGrpc(ResourceAgent):
    def __init__(self, grpc_channel: Channel, metadata=None):
        self._channel = grpc_channel
        self._service = pb_res.ResourceServiceStub(self._channel, metadata=metadata)

    async def list_resource_infos(self) -> list[ResourceInfo]:
        req = pb_res.ListResourcesRequest()
        resp = await self._service.list_resources(req)
        return [resource_info_from_pb(r) for r in resp.resources]

    async def deploy_instruments(
        self,
        port_id: ResourceId,
        definitions: Collection[InstrumentDefinition],
        append: bool,
        session_token: SessionToken,
    ) -> list[InstrumentInfo]:
        definitions_pb = list(map(instrument_definition_to_pb, definitions))
        req = pb_res.DeployInstrumentsRequest(
            port_id=port_id,
            definitions=definitions_pb,
            append=append,
            session_token=str(session_token),
        )
        resp = await self._service.deploy_instruments(req)
        insts = list(map(instrument_from_pb, resp.instruments))
        return insts

    async def get_port_info(self, resource_id: ResourceId) -> PortInfo:
        req = pb_res.GetPortRequest(id=resource_id)
        resp = await self._service.get_port(req)
        if resp.port is None:
            raise ValueError("port is not set.")
        return PortInfo(
            id=ResourceId(resp.port.id), role=port_role_from_pb(resp.port.role)
        )

    async def get_instrument_info(self, resource_id: ResourceId) -> InstrumentInfo:
        req = pb_res.GetInstrumentRequest(id=resource_id)
        resp = await self._service.get_instrument(req)
        if resp.instrument is None:
            raise ValueError("instrument is not set.")
        return instrument_from_pb(resp.instrument)


__all__ = ["ResourceAgentGrpc"]
