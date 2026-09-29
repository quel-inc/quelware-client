"""quel-trigger-wait-test: how short a trigger wait the units start in time on.

Puts a transmitter on every tx/trx port of the units and triggers them all at
once, over and over, at each of a set of waits between the trigger and the
start, one after another in turn, then reports for each wait how many runs
completed and what the others failed on. Without ``--unit`` it runs on every
unit the manager knows; one unit is triggered by itself, several through the
manager. Exits non-zero if any run failed.
"""

import asyncio
import logging
import statistics
from typing import Annotated

import typer
from quelware_client.client import create_quelware_client
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics.trigger_wait_test import (
    DEFAULT_WAITS_MS,
    run_trigger_wait_test,
)

logger = logging.getLogger(__name__)


def _entry(  # noqa: PLR0913
    host: Annotated[str, typer.Argument(help="manager host")],
    unit: Annotated[
        list[str] | None,
        typer.Option(help="unit label to run on, repeatable (default: every unit)"),
    ] = None,
    port: Annotated[int, typer.Option(help="manager port")] = 50051,
    pat: Annotated[
        str | None, typer.Option(help="PAT; defaults to the configured PAT")
    ] = None,
    wait_ms: Annotated[
        list[int] | None,
        typer.Option(help="trigger wait to try in ms, repeatable"),
    ] = None,
    runs_per_wait: Annotated[int, typer.Option(help="runs at each wait")] = 20,
    tx_hz: Annotated[float, typer.Option(help="transmit frequency in Hz")] = 5.1e9,
    discard_instruments: Annotated[
        bool,
        typer.Option(help="discard instruments already on the units before starting"),
    ] = False,
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Run the trigger wait test on QuEL-3 units."""
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        qc = create_quelware_client(host, port, pat=pat)
        async with qc:
            report = await run_trigger_wait_test(
                qc,
                [UnitLabel(u) for u in unit] if unit else None,
                waits_ms=wait_ms or DEFAULT_WAITS_MS,
                runs_per_wait=runs_per_wait,
                tx_hz=tx_hz,
                discard_instruments=discard_instruments,
            )
        print(f"{report.ports} ports on {', '.join(report.unit_labels)}")
        for r in report.results:
            trigger = (
                f"trigger {statistics.median(r.trigger_sec):.2f} s"
                if r.trigger_sec
                else "no trigger"
            )
            reasons = ", ".join(f"{k} {n}" for k, n in r.failures.most_common())
            print(
                f"  {r.wait_ms:5d} ms: {r.completed}/{r.runs} completed, {trigger}"
                + (f"; failed on {reasons}" if reasons else "")
            )
        if any(r.failed for r in report.results):
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
