import quelware_core.pb.quelware.system_configuration.v1 as pb_conf
from betterproto2.grpclib.grpclib_client import MetadataLike
from grpclib.client import Channel
from quelware_core.entities.unit import UnitLabel

from quelware_client.core.interfaces.system_configuration_agent import (
    SystemConfigurationAgent,
)
from quelware_client.infra._grpc_retry import call_with_retry


class SystemConfigurationAgentGrpc(SystemConfigurationAgent):
    def __init__(self, grpc_channel: Channel, metadata: MetadataLike | None = None):
        self._channel = grpc_channel
        self._service = pb_conf.SystemConfigurationServiceStub(
            self._channel, metadata=metadata
        )

    async def list_units(self) -> list[UnitLabel]:
        req = pb_conf.ListUnitsRequest()
        response = await call_with_retry(
            lambda: self._service.list_units(req), idempotent=True
        )

        return list(UnitLabel(u.label) for u in response.units)


__all__ = ["SystemConfigurationAgentGrpc"]
