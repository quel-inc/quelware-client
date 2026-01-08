import quelware_core.pb.quelware.models.v1 as pb_models
import quelware_core.pb.quelware.system_configuration.v1 as pb_conf
from grpclib.client import Channel
from quelware_core.entities.unit import UnitLabel

from quelware_client.core.interfaces.system_configuration_agent import (
    SystemConfigurationAgent,
)


class SystemConfigurationAgentGrpc(SystemConfigurationAgent):
    def __init__(self, grpc_channel: Channel):
        self._channel = grpc_channel
        self._service = pb_conf.SystemConfigurationServiceStub(self._channel)

    async def list_active_units(self) -> list[UnitLabel]:
        req = pb_conf.ListUnitsRequest()
        response = await self._service.list_units(req)

        return list(
            UnitLabel(u.label)
            for u in response.units
            if u.status is pb_models.UnitStatus.ACTIVE
        )


__all__ = ["SystemConfigurationAgentGrpc"]
