"""QuEL-3 monitor-loopback plumbing shared by the per-port diagnostics.

The monitor is a unit control keyed ``quel3.monitor.mode``; emitting ports are
named ``trx*``/``tx*`` and the monitor capture port ends ``:mon``.
"""

import logging

from quelware_client.core import QuelwareClient
from quelware_core.entities.resource import ResourceCategory, ResourceId
from quelware_core.entities.unit import UnitLabel

logger = logging.getLogger(__name__)

MONITOR_MODE_KEY = "quel3.monitor.mode"
MON_PORT_SUFFIX = ":mon"
EMIT_PORT_PREFIXES = ("trx", "tx")


async def port_ids(client: QuelwareClient) -> list[ResourceId]:
    rinfos = await client.list_resource_infos()
    return [r.id for r in rinfos if r.category == ResourceCategory.PORT]


def port_name(port_id: ResourceId) -> str:
    return str(port_id).rsplit(":", 1)[-1]


async def emit_ports(client: QuelwareClient) -> list[ResourceId]:
    ports = [
        p for p in await port_ids(client) if port_name(p).startswith(EMIT_PORT_PREFIXES)
    ]
    if not ports:
        raise RuntimeError("no tx/trx ports found on the unit")
    return ports


async def monitor_port(client: QuelwareClient) -> ResourceId:
    mon = next(
        (p for p in await port_ids(client) if str(p).endswith(MON_PORT_SUFFIX)), None
    )
    if mon is None:
        raise RuntimeError("monitor port not found after enabling loopback")
    return mon


async def discard_all_instruments(client: QuelwareClient) -> None:
    ports = await port_ids(client)
    async with client.create_session(ports) as session:
        for port_id in ports:
            logger.info("discarding instruments on %s", port_id)
            await session.discard_instruments(port_id)


async def set_monitor_loopback(client: QuelwareClient, unit_label: UnitLabel) -> None:
    logger.info("setting monitor to loopback on %s", unit_label)
    async with client.create_session(await port_ids(client)) as session:
        await session.configure_unit(unit_label, {MONITOR_MODE_KEY: "loopback"})


async def restore_monitor_open(
    client: QuelwareClient,
    unit_label: UnitLabel,
    deployed_ports: list[ResourceId],
) -> None:
    async with client.create_session(await port_ids(client)) as session:
        for port_id in deployed_ports:
            logger.info("discarding instruments on %s", port_id)
            await session.discard_instruments(port_id)
        logger.info("restoring monitor to open on %s", unit_label)
        await session.configure_unit(unit_label, {MONITOR_MODE_KEY: "open"})


__all__ = [
    "EMIT_PORT_PREFIXES",
    "MONITOR_MODE_KEY",
    "MON_PORT_SUFFIX",
    "discard_all_instruments",
    "emit_ports",
    "monitor_port",
    "port_ids",
    "port_name",
    "restore_monitor_open",
    "set_monitor_loopback",
]
