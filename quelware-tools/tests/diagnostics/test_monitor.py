from typing import cast

import pytest
from quelware_client.core import QuelwareClient
from quelware_core.entities.resource import ResourceCategory, ResourceId, ResourceInfo
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics import _monitor

_UNIT = UnitLabel("quel3-01-a28")
_OTHER = UnitLabel("quel3-02-b31")


def _all_infos() -> list[ResourceInfo]:
    """Resources as one manager serving two units would report them."""
    return [
        ResourceInfo(ResourceId(f"{_UNIT}:trx0"), ResourceCategory.PORT),
        ResourceInfo(ResourceId(f"{_UNIT}:tx1"), ResourceCategory.PORT),
        ResourceInfo(ResourceId(f"{_UNIT}:rx2"), ResourceCategory.PORT),
        ResourceInfo(ResourceId(f"{_UNIT}:mon"), ResourceCategory.PORT),
        ResourceInfo(ResourceId(f"{_UNIT}:trx0:inst"), ResourceCategory.INSTRUMENT),
        ResourceInfo(ResourceId(f"{_OTHER}:trx0"), ResourceCategory.PORT),
        ResourceInfo(ResourceId(f"{_OTHER}:tx1"), ResourceCategory.PORT),
        ResourceInfo(ResourceId(f"{_OTHER}:mon"), ResourceCategory.PORT),
    ]


class _FakeClient:
    def __init__(self, infos: list[ResourceInfo]) -> None:
        self._infos = infos

    async def list_resource_infos(self) -> list[ResourceInfo]:
        return self._infos


def _client(infos: list[ResourceInfo] | None = None) -> QuelwareClient:
    fake = _FakeClient(_all_infos() if infos is None else infos)
    return cast(QuelwareClient, fake)


@pytest.mark.asyncio
async def test_port_ids_only_from_target_unit() -> None:
    assert await _monitor.port_ids(_client(), _UNIT) == [
        f"{_UNIT}:trx0",
        f"{_UNIT}:tx1",
        f"{_UNIT}:rx2",
        f"{_UNIT}:mon",
    ]


@pytest.mark.asyncio
async def test_emit_ports_skips_other_unit_and_rx() -> None:
    assert await _monitor.emit_ports(_client(), _UNIT) == [
        f"{_UNIT}:trx0",
        f"{_UNIT}:tx1",
    ]


@pytest.mark.asyncio
async def test_emit_ports_raises_for_unknown_unit() -> None:
    with pytest.raises(RuntimeError, match="no tx/trx ports"):
        await _monitor.emit_ports(_client(), UnitLabel("quel3-99-zzz"))


@pytest.mark.asyncio
async def test_monitor_port_picks_own_unit_not_the_first_mon() -> None:
    """The other unit's ``:mon`` must never win, whatever the listing order."""
    client = _client(list(reversed(_all_infos())))
    assert await _monitor.monitor_port(client, _UNIT) == f"{_UNIT}:mon"
    assert await _monitor.monitor_port(client, _OTHER) == f"{_OTHER}:mon"


@pytest.mark.asyncio
async def test_monitor_port_raises_for_unit_without_mon() -> None:
    client = _client(
        [r for r in _all_infos() if not str(r.id).endswith(_monitor.MON_PORT_SUFFIX)]
    )
    with pytest.raises(RuntimeError, match="monitor port not found"):
        await _monitor.monitor_port(client, _UNIT)


def test_resolve_port_accepts_own_full_id() -> None:
    assert _monitor.resolve_port(_UNIT, f"{_UNIT}:trx0") == f"{_UNIT}:trx0"


def test_resolve_port_rejects_other_unit() -> None:
    with pytest.raises(ValueError, match="belongs to unit"):
        _monitor.resolve_port(_UNIT, f"{_OTHER}:trx0")


def test_resolve_port_rejects_bare_name() -> None:
    with pytest.raises(ValueError, match="full resource id"):
        _monitor.resolve_port(_UNIT, "trx0")
