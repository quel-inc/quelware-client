import argparse
import asyncio
import logging

import numpy as np
from quelware_core.entities import directives
from quelware_core.entities.directives import CaptureMode
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentMode,
    InstrumentRole,
)

from quelware_client.client import create_quelware_client, create_standalone_client
from quelware_client.client.helpers.instrument_resolver import InstrumentResolver
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)

logger = logging.getLogger(__name__)


async def generate_readout_pulse(
    unit_label: str,
    average_on_dsp: bool,
    use_standalone: bool = False,
    server_host: str = "localhost",
    server_port: int = 50051,
):
    if use_standalone:
        qc = create_standalone_client(server_host, server_port, unit_label=unit_label)
    else:
        qc = create_quelware_client(server_host, server_port)

    port_id = f"{unit_label}:trx_p00p01"
    instrument_alias = "readout"

    async with qc:
        async with qc.create_session([port_id]) as session:
            profile = FixedTimelineProfile(
                frequency_range_min=5.9e9, frequency_range_max=6.1e9
            )

            definition = InstrumentDefinition(
                alias=instrument_alias,
                mode=InstrumentMode.FIXED_TIMELINE,
                role=InstrumentRole.TRANSCEIVER,
                profile=profile,
            )

            inst_infos = await session.deploy_instruments(
                port_id, definitions=[definition]
            )
            deployed_inst_info = inst_infos[0]
            inst_id = deployed_inst_info.id
            print(f"Successfully deployed: {inst_id}")

        print("--- instrument info. ---")
        print(f"id\t= {deployed_inst_info.id}")
        print(f"alias\t= {deployed_inst_info.definition.alias}")
        print(f"sampling_period_fs\t= {deployed_inst_info.config.sampling_period_fs}")
        print("------------------------")

        async with qc.create_session([inst_id]) as session:
            resolver = InstrumentResolver()
            await resolver.refresh(qc)

            inst_info = resolver.find_inst_info_by_alias(instrument_alias)
            driver = create_instrument_driver_fixed_timeline(session, inst_info)

            seq = Sequencer(default_sampling_period_ns=0.4, enforce_sample_grid=True)

            seq.bind(
                alias=instrument_alias,
                sampling_period_fs=driver.instrument_config.sampling_period_fs,
                step_samples=driver.instrument_config.timeline_step_samples,
            )

            pulse_len_ns = 200.0
            wait_len_ns = 100_000.0

            num_samples = int(pulse_len_ns / 0.4)
            seq.register_waveform("rect_pulse", np.array([1.0 + 0j] * num_samples))

            seq.add_event(instrument_alias, "rect_pulse", start_offset_ns=0.0)
            # start_offset_ns=0.1 fails when enforce_sample_grid=True
            seq.add_capture_window(
                instrument_alias, "window1", start_offset_ns=0.0, length_ns=pulse_len_ns
            )

            seq.extend_length_ns(wait_len_ns)
            seq.set_iterations(1000)

            await driver.apply([directives.SetFrequency(hz=6.0e9)])
            if average_on_dsp:
                await driver.apply(
                    directives.SetCaptureMode(mode=CaptureMode.AVERAGED_VALUE)
                )
            else:
                await driver.apply(
                    directives.SetCaptureMode(mode=CaptureMode.RAW_WAVEFORMS)
                )

            timeline = seq.export_set_fixed_timeline_directive(instrument_alias)
            print(timeline.length % 128)
            print(timeline.length)
            await driver.apply(timeline)

            await session.trigger([inst_id])
            result = await driver.fetch_result()
            data = result.iq_result["window1"]

            if average_on_dsp:
                print(f"DSP Average Result: {data[0]}")
            else:
                print(f"Single Shot Data Count: {len(data)}")


def main():
    parser = argparse.ArgumentParser(
        description="Quelware Pulse Generation Test Script"
    )
    parser.add_argument("unit_label", type=str, help="Unit label (e.g., quel3-xx-yyy)")
    parser.add_argument(
        "--use-standalone-client",
        action="store_true",
        help="Use standalone client mode",
    )
    parser.add_argument(
        "--single-shot",
        action="store_true",
        help="Disable DSP averaging (default: enabled)",
    )
    parser.add_argument("--host", type=str, default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=50051, help="Server port")

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    asyncio.run(
        generate_readout_pulse(
            unit_label=args.unit_label,
            average_on_dsp=not args.single_shot,
            use_standalone=args.use_standalone_client,
            server_host=args.host,
            server_port=args.port,
        )
    )


if __name__ == "__main__":
    main()
