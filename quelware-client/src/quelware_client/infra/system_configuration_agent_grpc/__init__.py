import quelware_core.pb.quelware.system_configuration.v1 as pb_conf
from betterproto2.grpclib.grpclib_client import MetadataLike
from grpclib.client import Channel
from quelware_core.entities.unit import UnitLabel

from quelware_client.core.interfaces.system_configuration_agent import (
    SystemConfigurationAgent,
)


class SystemConfigurationAgentGrpc(SystemConfigurationAgent):
    def __init__(self, grpc_channel: Channel, metadata: MetadataLike | None = None):
        self._channel = grpc_channel
        self._service = pb_conf.SystemConfigurationServiceStub(
            self._channel, metadata=metadata
        )

    async def list_units(self) -> list[UnitLabel]:
        req = pb_conf.ListUnitsRequest()
        response = await self._service.list_units(req)

        return list(UnitLabel(u.label) for u in response.units)


__all__ = ["SystemConfigurationAgentGrpc"]
