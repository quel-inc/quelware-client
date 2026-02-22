import asyncio

import typer
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceCategory, ResourceId, ResourceInfo
from quelware_core.entities.unit import UnitLabel, UnitStatus

from quelware_client.testing import create_mock_quelware_client


async def _main_async():
    unit = UnitLabel("mock-quel3-1")
    unit_status = {unit: UnitStatus.ACTIVE}

    rsrcs = {
        unit: [
            ResourceInfo(
                id=ResourceId(f"{unit}:p0_trx"), category=ResourceCategory.PORT
            )
        ]
    }

    async with create_mock_quelware_client(unit_status, rsrcs) as client:
        infos = await client.list_resource_infos()
        assert len(infos) == 1
        port_id = infos[0].id

        async with client.create_session([port_id]) as session:
            assert session.token is not None

            definition = InstrumentDefinition(
                alias="test-readout",
                mode=InstrumentMode.FIXED_TIMELINE,
                role=InstrumentRole.TRANSCEIVER,
                profile=FixedTimelineProfile(4e9, 6e9),
            )

            inst_infos = await session.deploy_instruments(port_id, [definition])
            assert len(inst_infos) == 1
            assert inst_infos[0].definition.alias == "test-readout"


def main():
    asyncio.run(_main_async())


if __name__ == "__main__":
    typer.run(main)
