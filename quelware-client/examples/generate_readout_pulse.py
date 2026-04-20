"""Generate a readout pulse and capture the result.

Notebook:
    Copy deploy_instrument() and run_readout() into your notebook cells.

    unit_label = "quel3-01-028"
    qc = create_quelware_client("localhost", 50051)
    async with qc:
        inst_id, inst_info = await deploy_instrument(
            qc, unit_label,
            frequency_hz=6.0e9,
            half_bandwidth_hz=2.5e6,
            loopback=True,
        )
        iq = await run_readout(
            qc, inst_id, inst_info,
            frequency_hz=6.0e9,
            pulse_len_ns=200.0,
            capture_delay_ns=0.0,
            capture_len_ns=1000.0,
            shot_gap_ns=100_000.0,
            n_shots=1000,
        )

    import matplotlib.pyplot as plt
    plt.plot(iq.real, label="I")
    plt.plot(iq.imag, label="Q")
    plt.legend()
    plt.show()

CLI:
    python generate_readout_pulse.py quel3-01-028
    python generate_readout_pulse.py quel3-01-028 --loopback
    python generate_readout_pulse.py quel3-01-028 --integrate
    python generate_readout_pulse.py quel3-01-028 --standalone
"""

import argparse
import asyncio
import logging

import numpy as np
from quelware_core.entities import directives
from quelware_core.entities.directives import CaptureMode
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceId

from quelware_client.client import create_quelware_client, create_standalone_client
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core import QuelwareClient
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 50051


async def deploy_instrument(
    qc: QuelwareClient,
    unit_label: str,
    alias: str = "readout",
    frequency_hz: float = 6.0e9,
    half_bandwidth_hz: float = 2.5e6,
    loopback: bool = False,
) -> tuple[ResourceId, InstrumentInfo]:
    """Deploy a transceiver instrument and return (inst_id, inst_info)."""
    port_id = f"{unit_label}:trx_p00p01"
    role = (
        InstrumentRole.TRANSCEIVER_LOOPBACK if loopback else InstrumentRole.TRANSCEIVER
    )

    async with qc.create_session([port_id]) as session:
        definition = InstrumentDefinition(
            alias=alias,
            mode=InstrumentMode.FIXED_TIMELINE,
            role=role,
            profile=FixedTimelineProfile(
                frequency_range_min=frequency_hz - half_bandwidth_hz,
                frequency_range_max=frequency_hz + half_bandwidth_hz,
            ),
        )
        inst_infos = await session.deploy_instruments(port_id, definitions=[definition])
    inst_info = inst_infos[0]
    logger.info("Deployed instrument: %s", inst_info.id)
    return inst_info.id, inst_info


async def run_readout(
    qc: QuelwareClient,
    inst_id: ResourceId,
    inst_info: InstrumentInfo,
    frequency_hz: float = 6.0e9,
    pulse_len_ns: float = 200.0,
    capture_delay_ns: float = 0.0,
    capture_len_ns: float = 1000.0,
    shot_gap_ns: float = 100_000.0,
    n_shots: int = 1000,
    capture_mode: CaptureMode = CaptureMode.AVERAGED_WAVEFORM,
) -> np.ndarray:
    """Run a readout pulse and return captured IQ data as a numpy array."""
    alias = inst_info.definition.alias
    sampling_period_ns = inst_info.config.sampling_period_fs * 1e-6

    capture_end_ns = capture_delay_ns + capture_len_ns
    timeline_len_ns = max(pulse_len_ns, capture_end_ns) + shot_gap_ns

    async with qc.create_session([inst_id], ttl_ms=10000) as session:
        driver = create_instrument_driver_fixed_timeline(session, inst_info)

        seq = Sequencer(
            default_sampling_period_ns=sampling_period_ns,
            enforce_sample_grid=True,
        )
        seq.bind(
            alias=alias,
            sampling_period_fs=inst_info.config.sampling_period_fs,
            step_samples=inst_info.config.timeline_step_samples,
        )

        n_samples = int(pulse_len_ns / sampling_period_ns)
        seq.register_waveform("rect_pulse", np.ones(n_samples, dtype=complex))
        seq.add_event(alias, "rect_pulse", start_offset_ns=0.0)
        seq.add_capture_window(
            alias,
            "capture",
            start_offset_ns=capture_delay_ns,
            length_ns=capture_len_ns,
        )
        seq.extend_length_ns(timeline_len_ns)
        seq.set_iterations(n_shots)

        await driver.initialize()
        await driver.apply(
            [
                directives.SetFrequency(hz=frequency_hz),
                directives.SetCaptureMode(mode=capture_mode),
                seq.export_set_fixed_timeline_directive(alias),
            ]
        )

        await session.trigger([inst_id])
        result = await driver.fetch_result()

    return result.iq_result["capture"][0].iq_array


def cli():
    parser = argparse.ArgumentParser(description="Generate a readout pulse")
    parser.add_argument("unit_label", help="Unit label (e.g., quel3-01-028)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument(
        "--standalone", action="store_true", help="Use standalone client"
    )
    parser.add_argument(
        "--loopback", action="store_true", help="Use internal loopback mode"
    )
    parser.add_argument("--frequency-ghz", type=float, default=6.0)
    parser.add_argument("--pulse-len-ns", type=float, default=200.0)
    parser.add_argument("--capture-delay-ns", type=float, default=0.0)
    parser.add_argument("--capture-len-ns", type=float, default=1000.0)
    parser.add_argument("--shot-gap-ns", type=float, default=100_000.0)
    parser.add_argument("--n-shots", type=int, default=1000)
    parser.add_argument(
        "--integrate", action="store_true", help="Use AVERAGED_VALUE capture mode"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    capture_mode = (
        CaptureMode.AVERAGED_VALUE if args.integrate else CaptureMode.AVERAGED_WAVEFORM
    )

    async def _run():
        if args.standalone:
            qc = create_standalone_client(
                args.host, args.port, unit_label=args.unit_label
            )
        else:
            qc = create_quelware_client(args.host, args.port)

        async with qc:
            inst_id, inst_info = await deploy_instrument(
                qc,
                args.unit_label,
                frequency_hz=args.frequency_ghz * 1e9,
                half_bandwidth_hz=1e9 / args.pulse_len_ns / 2,
                loopback=args.loopback,
            )
            iq = await run_readout(
                qc,
                inst_id,
                inst_info,
                frequency_hz=args.frequency_ghz * 1e9,
                pulse_len_ns=args.pulse_len_ns,
                capture_delay_ns=args.capture_delay_ns,
                capture_len_ns=args.capture_len_ns,
                shot_gap_ns=args.shot_gap_ns,
                n_shots=args.n_shots,
                capture_mode=capture_mode,
            )
        print(f"Captured {len(iq)} samples")
        print(f"Mean amplitude: {np.abs(iq).mean():.6f}")

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
