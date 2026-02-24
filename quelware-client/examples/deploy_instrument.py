import asyncio

import typer
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentMode,
    InstrumentRole,
)

from quelware_client.client import create_quelware_client
from quelware_client.client.helpers.instrument_resolver import InstrumentResolver
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)


async def _main_async(server_host: str, server_port: int):
    inst_resolver = InstrumentResolver()

    async with create_quelware_client(server_host, server_port) as qc:
        port_id = "quel3-00-123:p0p1trx"
        instrument_alias = "readout"
        async with qc.create_session(port_id) as session:
            profile = FixedTimelineProfile(
                frequency_range_min=4_000_000_000, frequency_range_max=4_200_000_000
            )
            inst_definitions = [
                InstrumentDefinition(
                    instrument_alias,
                    InstrumentMode.FIXED_TIMELINE,
                    InstrumentRole.TRANSCEIVER,
                    profile,
                )
            ]
            await session.deploy_instruments(port_id, definitions=inst_definitions)

        await inst_resolver.refresh(qc)

        async with qc.create_session(
            inst_resolver.resolve([instrument_alias])
        ) as session:
            driver = create_instrument_driver_fixed_timeline(
                session, inst_resolver.find_inst_info_by_alias(instrument_alias)
            )
            # await driver.apply(...)


def main(server_host: str, server_port: int):
    asyncio.run(_main_async(server_host=server_host, server_port=server_port))


if __name__ == "__main__":
    typer.run(main)
