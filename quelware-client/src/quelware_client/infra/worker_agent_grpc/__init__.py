from collections.abc import Mapping

import quelware_core.pb.quelware.worker.v1 as pb_worker
from grpclib.client import Channel
from quelware_core.entities.clock import CurrentCount, ReferenceCount
from quelware_core.entities.session import SessionToken
from typing_extensions import override

from quelware_client.core.interfaces.worker_agent import WorkerAgent
from quelware_client.core.unit_control import UnitConfiguration, UnitControlSpec
from quelware_client.infra._grpc_retry import call_with_retry
from quelware_client.infra._timeouts import (
    CALL_TIMEOUT_SEC,
    CONFIGURE_UNIT_TIMEOUT_SEC,
)


class WorkerAgentGrpc(WorkerAgent):
    def __init__(self, grpc_channel: Channel, metadata=None):
        self._channel = grpc_channel
        self._service = pb_worker.WorkerServiceStub(
            self._channel, metadata=metadata, timeout=CALL_TIMEOUT_SEC
        )

    @override
    async def get_clock_snapshot(self) -> tuple[CurrentCount, ReferenceCount]:
        req = pb_worker.GetClockSnapshotRequest()
        resp = await call_with_retry(
            lambda: self._service.get_clock_snapshot(req), idempotent=True
        )
        return (resp.current_count, resp.reference_count)

    @override
    async def get_unit_configuration(self) -> UnitConfiguration:
        req = pb_worker.GetUnitConfigurationRequest()
        resp = await call_with_retry(
            lambda: self._service.get_unit_configuration(req), idempotent=True
        )
        return UnitConfiguration(
            supported=tuple(
                UnitControlSpec(
                    key=spec.key,
                    allowed_values=tuple(spec.allowed_values),
                    current_value=spec.current_value,
                )
                for spec in resp.supported
            )
        )

    @override
    async def configure_unit(
        self, controls: Mapping[str, str], session_token: SessionToken
    ) -> dict[str, str]:
        req = pb_worker.ConfigureUnitRequest(controls=dict(controls))
        metadata = dict(self._service.metadata or {})
        metadata["x-session-token"] = str(session_token)
        resp = await call_with_retry(
            lambda: self._service.configure_unit(
                req, metadata=metadata, timeout=CONFIGURE_UNIT_TIMEOUT_SEC
            )
        )
        return dict(resp.controls)


__all__ = ["WorkerAgentGrpc"]
