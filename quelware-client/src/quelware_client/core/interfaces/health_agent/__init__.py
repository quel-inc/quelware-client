from typing import Protocol


class HealthAgent(Protocol):
    async def check(self) -> bool: ...
