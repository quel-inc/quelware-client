from typing import Protocol

from quelware_core.entities.resource import ResourceId


class DiagnosticsAgent(Protocol):
    async def dump_port_state(self, port_id: ResourceId) -> str: ...


__all__ = ["DiagnosticsAgent"]
