"""quel3-echo-test: emit a pulse on a TRX port and capture the echoed response."""

import asyncio
import logging
from typing import Annotated

import matplotlib.pyplot as plt
import numpy as np
import typer
from quelware_core.entities import directives
from quelware_core.entities.directives import CaptureMode
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.port import PortRole
from quelware_core.entities.resource import ResourceCategory, ResourceId

from quelware_client.client import create_quelware_client
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core import QuelwareClient
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)

logger = logging.getLogger(__name__)

_ALIAS = "echo_test"
_HALF_BW_HZ = 2.5e6


async def _resolve_port(qc: QuelwareClient, port_id: str | None) -> ResourceId:
    if port_id is not None:
        return ResourceId(port_id)
    for info in await qc.list_resource_infos():
        if info.category is not ResourceCategory.PORT:
            continue
        port_info = await qc.get_port_info(info.id)
        if port_info.role is PortRole.TRANSCEIVER:
            return info.id
    raise RuntimeError("no TRX port found on any reachable unit")


async def _deploy(
    qc: QuelwareClient,
    port_id: ResourceId,
    frequency_hz: float,
    loopback: bool,
) -> tuple[ResourceId, InstrumentInfo]:
    role = (
        InstrumentRole.TRANSCEIVER_LOOPBACK if loopback else InstrumentRole.TRANSCEIVER
    )
    async with qc.create_session([port_id]) as session:
        definition = InstrumentDefinition(
            alias=_ALIAS,
            mode=InstrumentMode.FIXED_TIMELINE,
            role=role,
            profile=FixedTimelineProfile(
                frequency_range_min=frequency_hz - _HALF_BW_HZ,
                frequency_range_max=frequency_hz + _HALF_BW_HZ,
            ),
        )
        inst_infos = await session.deploy_instruments(port_id, definitions=[definition])
    inst_info = inst_infos[0]
    logger.info("Deployed instrument: %s", inst_info.id)
    return inst_info.id, inst_info


async def _run(
    qc: QuelwareClient,
    inst_id: ResourceId,
    inst_info: InstrumentInfo,
    frequency_hz: float,
    pulse_len_samples: int,
    capture_start_offset_samples: int,
    capture_len_samples: int,
    shot_gap_ns: float,
    iterations: int,
) -> np.ndarray:
    sampling_period_ns = inst_info.config.sampling_period_fs * 1e-6
    pulse_len_ns = pulse_len_samples * sampling_period_ns
    capture_delay_ns = capture_start_offset_samples * sampling_period_ns
    capture_len_ns = capture_len_samples * sampling_period_ns
    timeline_len_ns = max(pulse_len_ns, capture_delay_ns + capture_len_ns) + shot_gap_ns

    async with qc.create_session([inst_id], ttl_ms=10000) as session:
        driver = create_instrument_driver_fixed_timeline(session, inst_info)
        seq = Sequencer(
            default_sampling_period_ns=sampling_period_ns,
            enforce_sample_grid=True,
        )
        seq.bind(
            alias=_ALIAS,
            sampling_period_fs=inst_info.config.sampling_period_fs,
            step_samples=inst_info.config.timeline_step_samples,
        )
        seq.register_waveform("rect_pulse", np.ones(pulse_len_samples, dtype=complex))
        seq.add_event(_ALIAS, "rect_pulse", start_offset_ns=0.0)
        seq.add_capture_window(
            _ALIAS,
            "capture",
            start_offset_ns=capture_delay_ns,
            length_ns=capture_len_ns,
        )
        seq.extend_length_ns(timeline_len_ns)
        seq.set_iterations(iterations)

        await driver.initialize()
        await driver.apply(
            [
                directives.SetFrequency(hz=frequency_hz),
                directives.SetCaptureMode(mode=CaptureMode.AVERAGED_WAVEFORM),
                seq.export_set_fixed_timeline_directive(_ALIAS),
            ]
        )
        await session.trigger([inst_id])
        result = await driver.fetch_result()

    return result.iq_waveform_result["capture"][0].iq_array


def _plot(iq: np.ndarray, save_path: str | None) -> None:
    fig, ax = plt.subplots()
    ax.plot(iq.real, label="I")
    ax.plot(iq.imag, label="Q")
    ax.set_xlabel("sample")
    ax.set_ylabel("amplitude")
    ax.legend()
    ax.set_title("echo test capture (averaged waveform)")
    if save_path is None:
        plt.show()
    else:
        fig.savefig(save_path)
        logger.info("saved plot to %s", save_path)
        plt.close(fig)


def _entry(
    host: Annotated[str, typer.Argument(help="server host")],
    port_id: Annotated[
        str | None,
        typer.Option(
            help="port resource id (e.g. quel3-01-a28:trx_p00p01); "
            "pick first reachable TRX port if omitted"
        ),
    ] = None,
    port: Annotated[int, typer.Option(help="server port")] = 50051,
    iterations: Annotated[
        int, typer.Option("--iter", help="number of pulses to average")
    ] = 1000,
    pulse_len_samples: Annotated[
        int, typer.Option(help="pulse length in samples")
    ] = 400,
    capture_start_offset: Annotated[
        int, typer.Option(help="capture window offset from pulse start, in samples")
    ] = 500,
    capture_len_samples: Annotated[
        int, typer.Option(help="capture window length in samples")
    ] = 1000,
    freq_hz: Annotated[float, typer.Option(help="carrier frequency in Hz")] = 6.0e9,
    shot_gap_ns: Annotated[
        float, typer.Option(help="gap between successive pulses, in ns")
    ] = 100_000.0,
    loopback: Annotated[bool, typer.Option(help="route TX into RX internally")] = False,
    iq_plot: Annotated[bool, typer.Option(help="show I/Q time-series plot")] = False,
    iq_plot_png: Annotated[
        str | None,
        typer.Option(
            metavar="PATH",
            help="save I/Q plot as PNG to PATH instead of displaying",
        ),
    ] = None,
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Emit a pulse on a TRX port and capture the echoed averaged response."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        qc = create_quelware_client(host, port)
        async with qc:
            resolved_port_id = await _resolve_port(qc, port_id)
            logger.info("using TRX port: %s", resolved_port_id)
            inst_id, inst_info = await _deploy(
                qc, resolved_port_id, frequency_hz=freq_hz, loopback=loopback
            )
            iq = await _run(
                qc,
                inst_id,
                inst_info,
                frequency_hz=freq_hz,
                pulse_len_samples=pulse_len_samples,
                capture_start_offset_samples=capture_start_offset,
                capture_len_samples=capture_len_samples,
                shot_gap_ns=shot_gap_ns,
                iterations=iterations,
            )
        print(f"captured {len(iq)} samples (mean |iq| = {np.abs(iq).mean():.6f})")
        if iq_plot_png is not None:
            _plot(iq, iq_plot_png)
        elif iq_plot:
            _plot(iq, None)

    asyncio.run(_main())


def cli() -> None:
    typer.run(_entry)


if __name__ == "__main__":
    cli()
