"""quel-pulse-test: per-port pulse test for a QuEL-3 unit.

Puts the unit's monitor into loopback and, for every tx/trx port, emits a train
of pulses of swept lengths and gaps and checks each shows up on the monitor
where it was put and as long as it was, and nothing else does. Requires an
admin PAT and an idle unit; the monitor is restored to ``open`` on the way out.
Exits non-zero if any port fails.
"""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import numpy as np
import typer
from quelware_client.client import create_quelware_client
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics import PortPulseResult, run_pulse_test
from quelware_tools.diagnostics.pulse_test import (
    DEFAULT_GAPS_TICKS,
    DEFAULT_LENGTHS_TICKS,
)

logger = logging.getLogger(__name__)


def _save_iq_plot(result: PortPulseResult, out_dir: Path) -> tuple[Path, Path]:
    """Write a port's capture as a PNG plot plus a raw ``.npy``: |IQ| against
    time, one row per run of pulses, the expected pulses shaded green, placed
    from the first seen one, and the seen ones orange, red when off."""
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    assert result.iq is not None and result.sample_rate_hz is not None
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = result.port_id.replace("/", "_").replace(":", "_") + ".pulse"
    iq = np.asarray(result.iq)
    npy_path, png_path = out_dir / f"{stem}.npy", out_dir / f"{stem}.png"
    np.save(npy_path, iq)

    t_ns = np.arange(iq.size) / result.sample_rate_hz * 1e9
    offset_ns = 0.0
    for m in result.matches:
        if m.measured is not None:
            offset_ns = m.measured.start_ns - m.expected.start_ns
            break
    rows: list[list] = []
    for m in result.matches:
        last = rows[-1][-1].expected if rows else None
        if last is None or m.expected.start_ns - last.start_ns - last.length_ns > 2000:
            rows.append([])
        rows[-1].append(m)

    mag = np.abs(iq)
    fig, axes = plt.subplots(len(rows), 1, figsize=(14, 2.2 * len(rows)), squeeze=False)
    for ax, row in zip(axes[:, 0], rows, strict=True):
        lo = row[0].expected.start_ns + offset_ns - 100
        hi = row[-1].expected.start_ns + row[-1].expected.length_ns + offset_ns + 100
        shown = (t_ns >= lo) & (t_ns <= hi)
        ax.plot(t_ns[shown], mag[shown], linewidth=0.6, color="black")
        for m in row:
            start = m.expected.start_ns + offset_ns
            ax.axvspan(start, start + m.expected.length_ns, color="green", alpha=0.2)
            if m.measured is not None:
                ax.axvspan(
                    m.measured.start_ns,
                    m.measured.start_ns + m.measured.length_ns,
                    ymin=0.9,
                    color="orange" if m.ok else "red",
                )
        for extra in result.extras:
            if lo <= extra.start_ns <= hi:
                ax.axvspan(
                    extra.start_ns,
                    extra.start_ns + extra.length_ns,
                    ymin=0.9,
                    color="red",
                )
        ax.set_xlim(lo, hi)
        ax.set_ylabel("|IQ|")
        ax.grid(True, alpha=0.3)
    axes[-1, 0].set_xlabel("Time (ns)")
    fig.suptitle(f"{result.port_id}: {'PASS' if result.passed else 'FAIL'}")
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    return png_path, npy_path


def _entry(  # noqa: PLR0913
    host: Annotated[str, typer.Argument(help="manager host")],
    unit: Annotated[str, typer.Option(help="unit label to check")],
    port: Annotated[int, typer.Option(help="manager port")] = 50051,
    pat: Annotated[
        str | None,
        typer.Option(help="admin PAT; defaults to the configured PAT"),
    ] = None,
    target_port: Annotated[
        str | None,
        typer.Option(
            help="restrict to one full port id on --unit "
            "(default: all tx/trx ports of the unit)"
        ),
    ] = None,
    tx_hz: Annotated[float, typer.Option(help="transmit frequency in Hz")] = 5.1e9,
    mon_hz: Annotated[float, typer.Option(help="monitor frequency in Hz")] = 5.0e9,
    length_ticks: Annotated[
        list[int] | None,
        typer.Option(help="pulse length in 3.2 ns ticks, repeatable"),
    ] = None,
    gap_ticks: Annotated[
        list[int] | None,
        typer.Option(help="gap after a pulse in 3.2 ns ticks, repeatable"),
    ] = None,
    tolerance_ns: Annotated[
        float, typer.Option(help="how far a pulse's start or length may be off")
    ] = 2.0,
    plot_iq: Annotated[
        Path | None,
        typer.Option(
            help="save each port's capture under DIR as a PNG plot and a raw .npy "
            "(needs the 'plot' extra)"
        ),
    ] = None,
    discard_instruments: Annotated[
        bool,
        typer.Option(help="discard instruments already on the unit before testing"),
    ] = False,
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Run the per-port pulse test on one QuEL-3 unit."""
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        qc = create_quelware_client(host, port, pat=pat)
        async with qc:
            report = await run_pulse_test(
                qc,
                UnitLabel(unit),
                port=target_port,
                tx_hz=tx_hz,
                mon_hz=mon_hz,
                lengths_ticks=length_ticks or DEFAULT_LENGTHS_TICKS,
                gaps_ticks=gap_ticks or DEFAULT_GAPS_TICKS,
                tolerance_ns=tolerance_ns,
                discard_instruments=discard_instruments,
            )
        for r in report.results:
            print(f"[{'PASS' if r.passed else 'FAIL'}] {r.port_id}: {r.detail}")
            if plot_iq is not None and r.iq is not None:
                png, npy = _save_iq_plot(r, plot_iq)
                print(f"  saved {png} and {npy}")
        passed_n = sum(r.passed for r in report.results)
        status = "PASS" if report.passed else "FAIL"
        print(f"[{status}] {report.unit_label}: {passed_n}/{len(report.results)} ports")
        if not report.passed:
            raise typer.Exit(code=1)

    try:
        asyncio.run(_main())
    except typer.Exit:
        raise
    except Exception as exc:
        message = getattr(exc, "message", None) or str(exc)
        typer.echo(f"error: {message}", err=True)
        raise typer.Exit(code=1) from exc


def cli() -> None:
    typer.run(_entry)


if __name__ == "__main__":
    cli()
