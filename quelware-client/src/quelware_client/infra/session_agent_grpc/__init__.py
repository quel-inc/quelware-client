from collections.abc import Collection

import quelware_core.pb.quelware.session.v1 as pb_session
from grpclib.client import Channel
from grpclib.const import Status
from grpclib.exceptions import GRPCError
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel
from quelware_core.grpc_helper.error import extract_obj

from quelware_client.core.exceptions import (
    InvalidTokenError,
    LockConflictError,
    QuelwareClientError,
    ResourceNotFoundError,
    UnitNotFoundError,
)
from quelware_client.core.interfaces.session_agent import (
    SessionAgent,
)


class SessionAgentGrpc(SessionAgent):
    def __init__(self, grpc_channel: Channel):
        self._channel = grpc_channel
        self._service = pb_session.SessionServiceStub(self._channel)

    async def open_session(
        self,
        resource_ids: Collection[ResourceId],
        tentative_ttl_ms: int,
        committed_ttl_ms: int,
    ) -> tuple[SessionToken, list[ResourceId]]:
        req = pb_session.OpenSessionRequest(
            resource_ids=list(resource_ids),
            tentative_ttl_ms=tentative_ttl_ms,
            committed_ttl_ms=committed_ttl_ms,
        )

        try:
            response = await self._service.open_session(req)
            return (
                SessionToken(response.token),
                [ResourceId(rid) for rid in response.resource_ids],
            )

        except GRPCError as e:
            self._handle_grpc_error(e)
            raise QuelwareClientError(f"Unexpected gRPC error: {e}") from e

    def _handle_grpc_error(self, e: GRPCError):
        resource_ids = []
        unit_labels = []
        if obj := extract_obj(e.details):
            if "resource_ids" in obj:
                resource_ids = [ResourceId(x) for x in obj["resource_ids"]]
            if "unit_labels" in obj:
                unit_labels = [UnitLabel(x) for x in obj["unit_labels"]]

        if e.status is Status.NOT_FOUND and unit_labels:
            raise UnitNotFoundError(e.message).with_unit_labels(unit_labels) from e
        elif e.status is Status.NOT_FOUND:
            raise ResourceNotFoundError(e.message).with_resource_ids(
                resource_ids
            ) from e
        elif e.status is Status.FAILED_PRECONDITION:
            raise LockConflictError(e.message).with_resource_ids(resource_ids) from e
        elif e.status is Status.UNAUTHENTICATED:
            raise InvalidTokenError(e.message) from e
        raise QuelwareClientError(e.message) from e

    async def close_session(self, token: SessionToken) -> bool:
        req = pb_session.CloseSessionRequest(session_token=token)
        await self._service.close_session(message=req)
        return True


__all__ = ["SessionAgentGrpc"]
