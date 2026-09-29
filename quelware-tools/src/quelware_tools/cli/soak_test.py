"""quel-soak-test: keep QuEL-3 units busy with random trains of waves on every port.

Runs random trains of waves on every tx/trx port of the units at once, every run
under one trigger, until the given number of runs or duration is spent (or until
interrupted). Without ``--unit`` it runs on every unit the manager knows. A run
refused before it starts counts as a pass; a run that fails, times out or breaks
otherwise is a failure. Requires idle tx/trx ports. Exits non-zero if any run
failed.
"""

import asyncio
import logging
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from quelware_client.client import create_quelware_client
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics import SoakProfile, run_soak_test

logger = logging.getLogger(__name__)


def _entry(  # noqa: PLR0913
    host: Annotated[str, typer.Argument(help="manager host")],
    unit: Annotated[
        list[str] | None,
        typer.Option(help="unit label to run on, repeatable (default: every unit)"),
    ] = None,
    port: Annotated[int, typer.Option(help="manager port")] = 50051,
    pat: Annotated[
        str | None,
        typer.Option(help="PAT; defaults to the configured PAT"),
    ] = None,
    runs: Annotated[
        int | None, typer.Option(help="number of runs (default: no limit)")
    ] = None,
    duration_sec: Annotated[
        float | None, typer.Option(help="stop after this many seconds")
    ] = None,
    seed: Annotated[int, typer.Option(help="random seed")] = 0,
    start_run: Annotated[
        int, typer.Option(help="index of the first run, to replay one")
    ] = 0,
    tx_hz: Annotated[float, typer.Option(help="transmit frequency in Hz")] = 5.1e9,
    span_ticks: Annotated[
        int,
        typer.Option(help="span every port's waves lie in, in 3.2 ns ticks"),
    ] = SoakProfile.span_ticks,
    save_dir: Annotated[
        Path | None, typer.Option(help="save each failed run's plan here as JSON")
    ] = None,
    stop_on_failure: Annotated[
        bool, typer.Option(help="stop at the first failed run")
    ] = False,
    report_every: Annotated[
        int, typer.Option(help="log a summary every this many runs")
    ] = 100,
    discard_instruments: Annotated[
        bool,
        typer.Option(help="discard instruments already on the units before starting"),
    ] = False,
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Run the soak test on QuEL-3 units, all at once."""
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    profile = SoakProfile(span_ticks=span_ticks)

    async def _main() -> None:
        qc = create_quelware_client(host, port, pat=pat)
        async with qc:
            report = await run_soak_test(
                qc,
                [UnitLabel(u) for u in unit] if unit else None,
                runs=runs,
                duration_sec=duration_sec,
                seed=seed,
                start_run=start_run,
                profile=profile,
                tx_hz=tx_hz,
                save_dir=save_dir,
                stop_on_failure=stop_on_failure,
                report_every=report_every,
                discard_instruments=discard_instruments,
            )
        print(
            f"{report.runs} runs on {', '.join(report.unit_labels)}: "
            f"{report.completed} completed, "
            f"{sum(report.refused.values())} refused, {len(report.failures)} failed"
        )
        for reason, count in report.refused.most_common():
            print(f"  refused {count}: {reason}")
        kinds = Counter(failure.kind for failure in report.failures)
        for kind, count in kinds.most_common():
            print(f"  failed {count}: {kind}")
        for failure in report.failures:
            print(f"  [FAIL] run {failure.run} {failure.kind}: {failure.detail}")
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
