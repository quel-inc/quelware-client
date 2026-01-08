import typer
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentMode,
    InstrumentRole,
)

from quelware_client.client import create_quelware_client
from quelware_client.client.helpers.instrument_mapper import InstrumentMapper
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)


async def main(server_host: str, server_port: int):
    async with create_quelware_client(server_host, server_port) as qc:
        mapper = InstrumentMapper()

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
            inst_infos = await session.deploy_instruments(
                port_id, definitions=inst_definitions
            )
            for inst_info in inst_infos:
                mapper.add_instrument_info(inst_info)

        alias_to_id = mapper.build_alias_to_id_map()
        async with qc.create_session(alias_to_id[instrument_alias]) as session:
            driver = create_instrument_driver_fixed_timeline(
                session, mapper.get_instrument_info(alias_to_id[instrument_alias])
            )
            # await driver.apply(...)


if __name__ == "__main__":
    typer.run(main)
