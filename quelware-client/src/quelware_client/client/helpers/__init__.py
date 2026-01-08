import asyncio
from collections.abc import Collection

from quelware_core.entities.instrument import InstrumentInfo
from quelware_core.entities.port import PortInfo
from quelware_core.entities.resource import (
    ResourceId,
)

from quelware_client.core import QuelwareClient


async def create_id_to_port_info_map(
    client: QuelwareClient, port_ids: Collection
) -> dict[ResourceId, PortInfo]:
    id_to_task = {}
    async with asyncio.TaskGroup() as tg:
        for port_id in port_ids:
            id_to_task[port_id] = tg.create_task(client.get_port_info(port_id))
    id_to_port_info = {rid: task.result() for rid, task in id_to_task.items()}
    return id_to_port_info


async def create_id_to_instrument_info_map(
    client: QuelwareClient, instrument_ids: Collection
) -> dict[ResourceId, InstrumentInfo]:
    id_to_task = {}
    async with asyncio.TaskGroup() as tg:
        for instrument_id in instrument_ids:
            id_to_task[instrument_id] = tg.create_task(
                client.get_instrument_info(instrument_id)
            )
    id_to_instrument_info = {rid: task.result() for rid, task in id_to_task.items()}
    return id_to_instrument_info


__all__ = ["create_id_to_instrument_info_map", "create_id_to_port_info_map"]
