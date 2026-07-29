"""quel-tone-test: per-port tone test for a QuEL-3 unit.

Puts the unit's monitor into loopback and, for every tx/trx port, emits a tone
and checks it appears in the monitor capture. Intended as a post-update health
check against a running system. Requires an admin PAT and an idle unit; the
monitor is restored to ``open`` on the way out. Exits non-zero if any port fails.
"""

import asyncio
import logging
from typing import Annotated

import typer
from quelware_client.client import create_quelware_client
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics import run_tone_test

logger = logging.getLogger(__name__)


def _entry(
    host: Annotated[str, typer.Argument(help="manager host")],
    unit: Annotated[str, typer.Option(help="unit label to check")],
    port: Annotated[int, typer.Option(help="manager port")] = 50051,
    pat: Annotated[
        str | None,
        typer.Option(help="admin PAT; defaults to the configured PAT"),
    ] = None,
    target_port: Annotated[
        str | None,
        typer.Option(help="restrict to one port id (default: all tx/trx ports)"),
    ] = None,
    tx_hz: Annotated[float, typer.Option(help="transmit frequency in Hz")] = 5.1e9,
    mon_hz: Annotated[float, typer.Option(help="monitor frequency in Hz")] = 5.0e9,
    threshold_db: Annotated[
        float, typer.Option(help="minimum tone peak-to-median in dB to pass")
    ] = 20.0,
    cw_length_ns: Annotated[
        float, typer.Option(help="length of the emitted CW in ns")
    ] = 4000.0,
    capture_start_ns: Annotated[
        float, typer.Option(help="capture window start offset in ns")
    ] = 1000.0,
    capture_length_ns: Annotated[
        float, typer.Option(help="capture window length in ns")
    ] = 800.0,
    iterations: Annotated[int, typer.Option(help="capture averaging iterations")] = 1,
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Run the per-port tone test on one QuEL-3 unit."""
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        qc = create_quelware_client(host, port, pat=pat)
        async with qc:
            report = await run_tone_test(
                qc,
                UnitLabel(unit),
                port=target_port,
                tx_hz=tx_hz,
                mon_hz=mon_hz,
                min_peak_to_median_db=threshold_db,
                cw_length_ns=cw_length_ns,
                capture_start_ns=capture_start_ns,
                capture_length_ns=capture_length_ns,
                iterations=iterations,
            )
        for r in report.results:
            print(f"[{'PASS' if r.passed else 'FAIL'}] {r.port_id}: {r.detail}")
        passed_n = sum(r.passed for r in report.results)
        status = "PASS" if report.passed else "FAIL"
        print(f"[{status}] {report.unit_label}: {passed_n}/{len(report.results)} ports")
        if not report.passed:
            raise typer.Exit(code=1)

    asyncio.run(_main())


def cli() -> None:
    typer.run(_entry)


if __name__ == "__main__":
    cli()
