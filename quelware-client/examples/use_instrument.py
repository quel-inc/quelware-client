import asyncio

import numpy as np
import typer
from quelware_core.entities import directives

from quelware_client.client import create_quelware_client
from quelware_client.client.helpers.instrument_resolver import InstrumentResolver
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)


async def _main_async(server_host: str, server_port: int):
    alias = "a-001-readinout"  # depends on previous deployments

    sequencer = Sequencer(default_sampling_period_ns=0.4)

    waveform_name = "pulse"
    sequencer.register_waveform(waveform_name, np.array([1.0] * 200))
    sequencer.add_event(
        alias, waveform_name, start_offset_ns=0.0, gain=1, phase_offset_deg=0
    )
    sequencer.add_event(
        alias, waveform_name, start_offset_ns=200.0, gain=0.5, phase_offset_deg=90
    )
    sequencer.add_capture_window(
        alias, "window1", start_offset_ns=200.0, length_ns=20.0
    )

    inst_resolver = InstrumentResolver()

    async with create_quelware_client(server_host, server_port) as qc:
        await inst_resolver.refresh(qc)

        async with qc.create_session(inst_resolver.resolve([alias])) as session:
            driver = create_instrument_driver_fixed_timeline(
                session, inst_resolver.find_inst_info_by_alias(alias)
            )
            await driver.apply(
                [
                    directives.SetFrequency(hz=4_000_000_000),
                    directives.SetPhaseOffset(degree=0),
                ]
            )
            await driver.apply(
                sequencer.export_set_fixed_timeline_directive(
                    alias, driver.instrument_config.sampling_period_fs
                )
            )
            await session.trigger(inst_resolver.resolve([alias]))

            result = await driver.fetch_result()
            iq_datas = result.iq_result["window1"]
            iq_data = iq_datas[0]


def main(server_host: str, server_port: int):
    asyncio.run(_main_async(server_host=server_host, server_port=server_port))


if __name__ == "__main__":
    typer.run(main)
