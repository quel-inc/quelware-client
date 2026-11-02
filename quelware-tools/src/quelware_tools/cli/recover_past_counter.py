"""quel-recover-past-counter: bring a unit back to normal after a run that
failed with past_counter, without a reboot.

A temporary workaround: it triggers every port of the units a few seconds
ahead and cancels the run on purpose before it starts. It replaces the
instruments on every port of the units and removes them at the end, so run it
only when nobody else uses the units. Exits non-zero if a cancel came too late
or a run failed otherwise.
"""

import asyncio
import logging
from typing import Annotated

import typer
from quelware_client.client import create_quelware_client
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics.recover_past_counter import (
    DEFAULT_CENTER_HZ,
    DEFAULT_WAIT_MS,
    run_recover_past_counter,
)

logger = logging.getLogger(__name__)


def _entry(  # noqa: PLR0913
    host: Annotated[str, typer.Argument(help="manager host")],
    unit: Annotated[list[str], typer.Option(help="unit label to recover, repeatable")],
    port: Annotated[int, typer.Option(help="manager port")] = 50051,
    pat: Annotated[
        str | None, typer.Option(help="PAT; defaults to the configured PAT")
    ] = None,
    wait_ms: Annotated[
        int,
        typer.Option(help="trigger wait; the cancel has to land within it"),
    ] = DEFAULT_WAIT_MS,
    center_hz: Annotated[
        float, typer.Option(help="center frequency of the instruments in Hz")
    ] = DEFAULT_CENTER_HZ,
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Bring QuEL-3 units back to normal after a run that failed with
    past_counter, without a reboot (a temporary workaround)."""
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        qc = create_quelware_client(host, port, pat=pat)
        async with qc:
            report = await run_recover_past_counter(
                qc,
                [UnitLabel(u) for u in unit],
                wait_ms=wait_ms,
                center_hz=center_hz,
            )
        units = ", ".join(report.unit_labels)
        if report.ok:
            print(
                f"[OK] Successfully cancelled the runs on every port of {units} "
                f"({report.ports} ports)"
            )
            return
        print(
            f"[FAIL] {units}: {report.cancelled} of {report.instruments} "
            f"instruments cancelled in time"
        )
        for alias in report.late:
            print(f"  {alias}: cancelled too late; run again with a longer --wait-ms")
        for alias, err in report.failed.items():
            print(f"  {alias}: failed: {err}")
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
