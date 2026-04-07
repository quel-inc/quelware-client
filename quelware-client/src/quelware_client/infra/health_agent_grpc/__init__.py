import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import betterproto2
from betterproto2 import grpclib as betterproto2_grpclib
from grpclib import GRPCError
from grpclib.client import Channel

from quelware_client.core.interfaces.health_agent import HealthAgent

logger = logging.getLogger(__name__)


@dataclass(eq=False, repr=False)
class HealthCheckRequest(betterproto2.Message):
    service: str = betterproto2.field(1, betterproto2.TYPE_STRING)


@dataclass(eq=False, repr=False)
class HealthCheckResponse(betterproto2.Message):
    class ServingStatus(betterproto2.Enum):
        UNKNOWN = 0
        SERVING = 1
        NOT_SERVING = 2
        SERVICE_UNKNOWN = 3

    status: "HealthCheckResponse.ServingStatus" = betterproto2.field(
        1, betterproto2.TYPE_ENUM, default_factory=int
    )


class HealthServiceStub(betterproto2_grpclib.ServiceStub):
    async def check(
        self,
        *,
        service: str = "",
        timeout: Optional[float] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> HealthCheckResponse:
        return await self._unary_unary(
            "/grpc.health.v1.Health/Check",
            HealthCheckRequest.from_dict({}),
            HealthCheckResponse,
            timeout=timeout,
            metadata=metadata,
        )


class HealthAgentGrpc(HealthAgent):
    def __init__(self, grpc_channel: Channel, metadata=None):
        self._channel = grpc_channel
        self._service = HealthServiceStub(self._channel, metadata=metadata)

    async def check(self) -> bool:
        try:
            resp = await self._service.check()
            match status := resp.status:
                case HealthCheckResponse.ServingStatus.SERVING:
                    logger.info(
                        "Passed health check: %s, %s",
                        str(status.__class__),
                        self._channel,
                    )
                    return True
                case _:
                    logger.warning(
                        "Unexpected status of health check: %s, %s",
                        str(status.__class__),
                        self._channel,
                    )
                    return False
        except GRPCError as exc:
            logger.error(
                "during health check error occured. status: %s, message: %s",
                exc.status,
                exc.message,
            )
            return False
