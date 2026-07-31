"""quel-measure-delay: per-port path-delay measurement for a QuEL-3 unit.

Puts the unit's monitor into loopback and, one tx/trx port at a time, emits a
pulse while capturing from t=0, timing the pulse's arrival to get the port ->
monitor path delay. Requires an admin PAT and an idle unit; the monitor is
restored to ``open`` on the way out. Exits non-zero if any port yields no pulse.
"""

import asyncio
import logging
from typing import Annotated

import typer
from quelware_client.client import create_quelware_client
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics import run_delay_test

logger = logging.getLogger(__name__)


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
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Measure the monitor path delay for each tx/trx port on one QuEL-3 unit."""
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

        status = "PASS" if report.passed else "FAIL"
        print(f"[{status}] {report.unit_label}")
        if not report.passed:
            raise typer.Exit(code=1)

    asyncio.run(_main())


def cli() -> None:
    typer.run(_entry)


if __name__ == "__main__":
    cli()
