from collections.abc import Collection

from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken

from quelware_client.core.interfaces.session_agent import (
    SessionAgent,
)


class SessionAgentMock(SessionAgent):
    open_session_result: tuple[SessionToken, list[ResourceId]]
    close_session_result: bool

    async def open_session(
        self,
        resource_ids: Collection[ResourceId],
        tentative_ttl_ms: int,
        committed_ttl_ms: int,
    ) -> tuple[SessionToken, list[ResourceId]]:
        return self.open_session_result

    async def close_session(self, token: SessionToken) -> bool:
        return self.close_session_result


__all__ = ["SessionAgentMock"]
