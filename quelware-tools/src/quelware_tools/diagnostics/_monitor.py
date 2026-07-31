"""QuEL-3 monitor-loopback plumbing shared by the per-port diagnostics.

The monitor is a unit control keyed ``quel3.monitor.mode``; emitting ports are
named ``trx*``/``tx*`` and the monitor capture port ends ``:mon``.

One manager can serve several units, so ``list_resource_infos`` returns the
whole system's resources. Every lookup here is therefore scoped to a single
``unit_label`` via :func:`extract_unit_label` -- picking up a neighbouring
unit's monitor would silently test the wrong signal path, and configuring or
discarding across units would disturb systems the caller never named.
"""

import logging

from quelware_client.core import QuelwareClient
from quelware_core.entities.resource import (
    ResourceCategory,
    ResourceId,
    extract_unit_label,
)
from quelware_core.entities.unit import UnitLabel

logger = logging.getLogger(__name__)

MONITOR_MODE_KEY = "quel3.monitor.mode"
MON_PORT_SUFFIX = ":mon"
EMIT_PORT_PREFIXES = ("trx", "tx")


async def port_ids(client: QuelwareClient, unit_label: UnitLabel) -> list[ResourceId]:
    """Every port belonging to ``unit_label``; other units are left alone."""
    rinfos = await client.list_resource_infos()
    return [
        r.id
        for r in rinfos
        if r.category == ResourceCategory.PORT
        and extract_unit_label(r.id) == unit_label
    ]


def port_name(port_id: ResourceId) -> str:
    return str(port_id).rsplit(":", 1)[-1]


def resolve_port(unit_label: UnitLabel, port: str) -> ResourceId:
    """Check a caller-supplied port id is a full id owned by ``unit_label``."""
    if ":" not in port:
        raise ValueError(
            f"port must be a full resource id such as '{unit_label}:{port}', "
            f"got {port!r}"
        )
    owner = extract_unit_label(ResourceId(port))
    if owner != unit_label:
        raise ValueError(
            f"port {port!r} belongs to unit {str(owner)!r}, not {str(unit_label)!r}"
        )
    return ResourceId(port)


async def emit_ports(client: QuelwareClient, unit_label: UnitLabel) -> list[ResourceId]:
    ports = [
        p
        for p in await port_ids(client, unit_label)
        if port_name(p).startswith(EMIT_PORT_PREFIXES)
    ]
    if not ports:
        raise RuntimeError(f"no tx/trx ports found on unit {unit_label}")
    return ports


async def monitor_port(client: QuelwareClient, unit_label: UnitLabel) -> ResourceId:
    mon = next(
        (
            p
            for p in await port_ids(client, unit_label)
            if str(p).endswith(MON_PORT_SUFFIX)
        ),
        None,
    )
    if mon is None:
        raise RuntimeError(
            f"monitor port not found on unit {unit_label} after enabling loopback"
        )
    return mon


async def discard_unit_instruments(
    client: QuelwareClient, unit_label: UnitLabel
) -> None:
    ports = await port_ids(client, unit_label)
    async with client.create_session(ports) as session:
        for port_id in ports:
            logger.info("discarding instruments on %s", port_id)
            await session.discard_instruments(port_id)


async def set_monitor_loopback(client: QuelwareClient, unit_label: UnitLabel) -> None:
    logger.info("setting monitor to loopback on %s", unit_label)
    async with client.create_session(await port_ids(client, unit_label)) as session:
        await session.configure_unit(unit_label, {MONITOR_MODE_KEY: "loopback"})


async def restore_monitor_open(
    client: QuelwareClient,
    unit_label: UnitLabel,
    deployed_ports: list[ResourceId],
) -> None:
    async with client.create_session(await port_ids(client, unit_label)) as session:
        for port_id in deployed_ports:
            logger.info("discarding instruments on %s", port_id)
            await session.discard_instruments(port_id)
        logger.info("restoring monitor to open on %s", unit_label)
        await session.configure_unit(unit_label, {MONITOR_MODE_KEY: "open"})


__all__ = [
    "EMIT_PORT_PREFIXES",
    "MONITOR_MODE_KEY",
    "MON_PORT_SUFFIX",
    "discard_unit_instruments",
    "emit_ports",
    "monitor_port",
    "port_ids",
    "port_name",
    "resolve_port",
    "restore_monitor_open",
    "set_monitor_loopback",
]
