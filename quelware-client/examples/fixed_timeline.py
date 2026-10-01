"""A drive pulse and a readout on fixed-timeline instruments.

The code of the fixed-timeline tutorial, which the docs quote from here. Run it
against your system:

    python fixed_timeline.py <host> --unit <label>
"""

# --8<-- [start:imports]
import argparse
import asyncio

import numpy as np
from quelware_core.entities import directives
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)

from quelware_client import create_quelware_client
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core import QuelwareClient, Session
from quelware_client.core.exceptions import RunFailedError
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)

# --8<-- [end:imports]


# --8<-- [start:deploy]
def definition(alias: str, role: InstrumentRole, center_hz: float):
    return InstrumentDefinition(
        alias=alias,
        mode=InstrumentMode.FIXED_TIMELINE,
        role=role,
        profile=FixedTimelineProfile(
            frequency_range_min=center_hz - 2.5e6,
            frequency_range_max=center_hz + 2.5e6,
        ),
    )


async def deploy(
    qc: QuelwareClient, drive_port: str, readout_port: str
) -> tuple[InstrumentInfo, InstrumentInfo]:
    async with qc.create_session([drive_port, readout_port]) as session:
        (drive,) = await session.deploy_instruments(
            drive_port, [definition("drive", InstrumentRole.TRANSMITTER, 5.0e9)]
        )
        (readout,) = await session.deploy_instruments(
            readout_port,
            [definition("readout", InstrumentRole.TRANSCEIVER_LOOPBACK, 6.0e9)],
        )
    return drive, readout


# --8<-- [end:deploy]


# --8<-- [start:timeline]
def build_timeline(
    inst_info: InstrumentInfo, pulse_start_ns: float, capture: bool
) -> Sequencer:
    alias = inst_info.definition.alias
    sampling_period_ns = inst_info.config.sampling_period_fs * 1e-6

    seq = Sequencer(default_sampling_period_ns=sampling_period_ns)
    seq.bind(
        alias,
        sampling_period_fs=inst_info.config.sampling_period_fs,
        step_samples=inst_info.config.timeline_step_samples,
    )

    n = int(200.0 / sampling_period_ns)  # a 200 ns rectangular pulse
    seq.register_waveform("pulse", np.ones(n, dtype=complex))
    seq.add_event(alias, "pulse", start_offset_ns=pulse_start_ns)
    if capture:
        seq.add_capture_window(
            alias, "capture", start_offset_ns=pulse_start_ns, length_ns=1000.0
        )
    seq.extend_length_ns(100_000.0)  # gap before the next shot
    seq.set_iterations(1000)  # average over 1000 shots
    return seq


# --8<-- [end:timeline]


# --8<-- [start:trigger]
async def configure(
    session: Session, inst_info: InstrumentInfo, hz: float, seq: Sequencer
) -> None:
    driver = create_instrument_driver_fixed_timeline(session, inst_info)
    alias = inst_info.definition.alias
    settings: list[directives.FixedTimelineDirective] = [directives.SetFrequency(hz=hz)]
    if inst_info.definition.role is not InstrumentRole.TRANSMITTER:
        settings.append(
            directives.SetCaptureMode(mode=directives.CaptureMode.AVERAGED_WAVEFORM)
        )
    settings.append(seq.export_set_fixed_timeline_directive(alias))
    await driver.initialize()
    await driver.apply(settings)


async def trigger(
    session: Session, drive: InstrumentInfo, readout: InstrumentInfo
) -> None:
    await configure(session, drive, 5.0e9, build_timeline(drive, 0.0, capture=False))
    await configure(
        session, readout, 6.0e9, build_timeline(readout, 300.0, capture=True)
    )
    await session.trigger([drive.id, readout.id])


# --8<-- [end:trigger]


# --8<-- [start:wait]
async def wait(
    session: Session, drive: InstrumentInfo, readout: InstrumentInfo
) -> np.ndarray:
    try:
        results = await session.wait_for_results(
            [drive.id, readout.id], timeout_sec=10.0
        )
    except RunFailedError as e:
        for instrument_id, error in e.failures.items():
            print(f"{instrument_id} failed: {error}")
        raise
    return results[readout.id].iq_waveform_result["capture"][0].iq_array


# --8<-- [end:wait]


# --8<-- [start:main]
async def main(host: str, port: int, drive_port: str, readout_port: str) -> None:
    qc = create_quelware_client(host, port)
    async with qc:
        drive, readout = await deploy(qc, drive_port, readout_port)
        async with qc.create_session([drive.id, readout.id], ttl_ms=10_000) as session:
            await trigger(session, drive, readout)
            iq = await wait(session, drive, readout)
    print(f"captured {len(iq)} samples")


# --8<-- [end:main]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run a drive pulse and a readout on fixed-timeline instruments."
    )
    parser.add_argument("host", help="server host")
    parser.add_argument("--port", type=int, default=50051, help="server port")
    parser.add_argument("--unit", required=True, help="unit label")
    parser.add_argument("--drive-port", default="tx_p02", help="a transmitter port")
    parser.add_argument(
        "--readout-port", default="trx_p00p01", help="a transceiver port"
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.host,
            args.port,
            f"{args.unit}:{args.drive_port}",
            f"{args.unit}:{args.readout_port}",
        )
    )
