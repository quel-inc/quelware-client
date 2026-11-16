from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from quelware_core.entities.clock import CurrentCount, ReferenceCount
from quelware_core.entities.session import SessionToken
from quelware_core.features import KNOWN, Feature

from quelware_client.core.unit_control import UnitConfiguration


@dataclass(frozen=True)
class UnitVersion:
    """What a unit runs, and the features it names that this client knows.

    A feature is a newer form of a message the unit accepts, such as
    ``"dense_waveform"`` for waveforms sent as bytes.
    """

    version: str
    features: frozenset[Feature] = frozenset()

    def supports(self, feature: Feature) -> bool:
        """Whether the unit named ``feature``; raises ValueError for an unknown one."""
        if feature not in KNOWN:
            raise ValueError(f"unknown feature: {feature!r}")
        return feature in self.features


class WorkerAgent(Protocol):
    async def get_version(self) -> UnitVersion | None:
        """The unit's version, or None when it does not answer."""
        ...

    async def get_clock_snapshot(self) -> tuple[CurrentCount, ReferenceCount]: ...

    async def get_unit_configuration(self) -> UnitConfiguration: ...

    async def configure_unit(
        self, controls: Mapping[str, str], session_token: SessionToken
    ) -> dict[str, str]: ...
