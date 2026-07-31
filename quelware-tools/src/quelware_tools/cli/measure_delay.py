"""quel-measure-delay: per-port path-delay measurement for a QuEL-3 unit.

Puts the unit's monitor into loopback and, one tx/trx port at a time, emits a
pulse while capturing from t=0, timing the pulse's arrival to get the port ->
monitor path delay. Requires an admin PAT and an idle unit; the monitor is
restored to ``open`` on the way out. Exits non-zero if any port yields no pulse.
"""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import numpy as np
import typer
from quelware_client.client import create_quelware_client
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics import CombVerification, run_delay_test

logger = logging.getLogger(__name__)


def _save_verify_iq_plot(
    v: CombVerification, out_dir: Path, unit_label: str
) -> tuple[Path, Path]:
    """Write the comb capture as a PNG plot plus a raw ``.npy``.

    Same layout as the edge-server hardware tests' ``--save-iq-plot``: |IQ| and
    phase against time, then the FFT magnitude. Expected arrivals are marked in
    green, measured ones in orange (red when out of tolerance).
    """
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = unit_label.replace("/", "_").replace(":", "_") + ".verify"
    iq = np.asarray(v.iq)
    npy_path = out_dir / f"{stem}.npy"
    png_path = out_dir / f"{stem}.png"
    np.save(npy_path, iq)

    t_ns = np.arange(len(iq)) / v.sample_rate_hz * 1e9
    spectrum_db = 20 * np.log10(np.fft.fftshift(np.abs(np.fft.fft(iq))) + 1e-12)
    freqs_mhz = np.fft.fftshift(np.fft.fftfreq(len(iq), d=1.0 / v.sample_rate_hz)) / 1e6

    fig, (ax_mag, ax_phase, ax_freq) = plt.subplots(3, 1, figsize=(10, 8))
    ax_mag.plot(t_ns, np.abs(iq), linewidth=0.6)
    for i, c in enumerate(v.checks):
        ax_mag.axvline(
            c.expected_ns,
            color="green",
            linestyle="--",
            linewidth=0.6,
            alpha=0.7,
            label="expected" if i == 0 else None,
        )
        if c.measured_ns is not None:
            ax_mag.axvline(
                c.measured_ns,
                color="orange" if c.ok else "red",
                linestyle=":",
                linewidth=0.8,
                alpha=0.8,
                label="measured" if i == 0 else None,
            )
    ax_mag.set_ylabel("|IQ|")
    ax_mag.grid(True, alpha=0.3)
    ax_mag.legend(loc="upper right", fontsize="small")

    ax_phase.plot(t_ns, np.angle(iq), linewidth=0.6)
    ax_phase.set_xlabel("Time (ns)")
    ax_phase.set_ylabel("Phase (rad)")
    ax_phase.grid(True, alpha=0.3)

    ax_freq.plot(freqs_mhz, spectrum_db, linewidth=0.6)
    ax_freq.set_xlabel("Baseband frequency (MHz)")
    ax_freq.set_ylabel("Magnitude (dB)")
    ax_freq.grid(True, alpha=0.3)

    fig.suptitle(
        f"{stem} (t_ref={v.t_ref_ns:.0f} ns, period={v.period_ns:.0f} ns, "
        f"tol=±{v.tolerance_samples:g} samples)"
    )
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    return png_path, npy_path


def _entry(
    host: Annotated[str, typer.Argument(help="manager host")],
    unit: Annotated[str, typer.Option(help="unit label to measure")],
    port: Annotated[int, typer.Option(help="manager port")] = 50051,
    pat: Annotated[
        str | None,
        typer.Option(help="admin PAT; defaults to the configured PAT"),
    ] = None,
    freq_hz: Annotated[float, typer.Option(help="carrier frequency in Hz")] = 5.0e9,
    pulse_length_ns: Annotated[
        float, typer.Option(help="length of the emitted pulse in ns")
    ] = 100.0,
    capture_length_ns: Annotated[
        float, typer.Option(help="capture window length in ns")
    ] = 2000.0,
    iterations: Annotated[int, typer.Option(help="capture averaging iterations")] = 1,
    threshold_db: Annotated[
        float, typer.Option(help="minimum pulse peak-to-noise in dB to detect")
    ] = 20.0,
    discard_instruments: Annotated[
        bool,
        typer.Option(help="discard instruments already on the unit before measuring"),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option(
            help="after measuring, deskew all ports onto a common comb, emit "
            "together, and check each pulse lands where intended"
        ),
    ] = False,
    tolerance_samples: Annotated[
        float, typer.Option(help="allowed pulse-position error in samples (verify)")
    ] = 2.0,
    verify_plot_iq: Annotated[
        str | None,
        typer.Option(
            metavar="DIR",
            help="save the verify comb capture under DIR as a PNG plot and a "
            "raw .npy (implies --verify; needs the 'plot' extra)",
        ),
    ] = None,
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Measure the monitor path delay for each tx/trx port on one QuEL-3 unit."""
    verify = verify or verify_plot_iq is not None
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        qc = create_quelware_client(host, port, pat=pat)
        async with qc:
            report = await run_delay_test(
                qc,
                UnitLabel(unit),
                freq_hz=freq_hz,
                pulse_length_ns=pulse_length_ns,
                capture_length_ns=capture_length_ns,
                iterations=iterations,
                min_snr_db=threshold_db,
                discard_instruments=discard_instruments,
                verify=verify,
                tolerance_samples=tolerance_samples,
            )
        for r in report.results:
            print(f"[{'OK' if r.detected else 'FAIL'}] {r.port_id}: {r.detail}")
        detected_n = sum(r.detected for r in report.results)
        n = len(report.results)
        print(f"delay: {detected_n}/{n} ports detected")

        v = report.verification
        if v is not None:
            print(
                f"comb verify (t_ref={v.t_ref_ns:.0f} ns, period={v.period_ns:.0f} ns, "
                f"tol=±{v.tolerance_samples:g} samples):"
            )
            for c in v.checks:
                if c.measured_ns is None:
                    print(f"  [FAIL] {c.port_id}: no pulse near {c.expected_ns:.1f} ns")
                else:
                    tag = "OK" if c.ok else "FAIL"
                    print(
                        f"  [{tag}] {c.port_id}: expected {c.expected_ns:.1f} ns, "
                        f"measured {c.measured_ns:.1f} ns "
                        f"(dev {c.deviation_samples:+.2f} samples)"
                    )

        if verify_plot_iq is not None:
            if v is None:
                print("no comb verification result to plot")
            else:
                png, npy = _save_verify_iq_plot(
                    v, Path(verify_plot_iq), report.unit_label
                )
                print(f"saved {png} and {npy}")

        status = "PASS" if report.passed else "FAIL"
        print(f"[{status}] {report.unit_label}")
        if not report.passed:
            raise typer.Exit(code=1)

    try:
        asyncio.run(_main())
    except typer.Exit:
        raise
    except Exception as exc:
        # gRPC errors carry a human message; fall back to the repr otherwise
        message = getattr(exc, "message", None) or str(exc)
        typer.echo(f"error: {message}", err=True)
        raise typer.Exit(code=1) from exc


def cli() -> None:
    typer.run(_entry)


if __name__ == "__main__":
    cli()
