"""quel-soak-test: keep QuEL-3 units busy with random trains of waves on every port.

Runs random trains of waves on every tx/trx port of the units at once, every run
under one trigger, a round of kinds by default, or the given number of rounds, runs
or seconds (or until interrupted). A round runs light kinds many times and heavy
kinds a few times, spread out: ``sparse``, waves of many lengths with gaps between
them; ``spectroscopy``, long capture windows repeated with a short blank;
``dense-cr``, a few flat pulses of 1 and 4 us; ``packed-sweep``, 50 calibration
points in one trigger; and ``packed-rb-1024`` and ``packed-rb-2048``, 30 randomized
benchmarking sequences of that many gates in one trigger. Without ``--unit`` it runs
on every unit the manager knows. A run refused before it starts counts as a pass; a
run that fails, times out or breaks otherwise is a failure. Requires idle tx/trx
ports. Exits non-zero if any run failed.

With ``--check-monitor``, the units are put in monitor loopback (an admin PAT is
needed, and every instrument on them is discarded) and back in open mode after, and
what each unit's monitor captures of one port shown at a time is judged against what
it sent; a run that comes back otherwise is a failure.
"""

import asyncio
import dataclasses
import logging
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from quelware_client.client import create_quelware_client
from quelware_core.entities.unit import UnitLabel

from quelware_tools.diagnostics import run_soak_test
from quelware_tools.diagnostics.soak_test import DEFAULT_ROUND, round_order

logger = logging.getLogger(__name__)

_KINDS = [e.kind for e in DEFAULT_ROUND]


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
    rounds: Annotated[
        int, typer.Option(help="number of rounds of the kinds to run")
    ] = 1,
    runs: Annotated[
        int | None,
        typer.Option(
            help="number of runs instead of rounds, 0 for no limit "
            "(no limit either with --duration-sec)"
        ),
    ] = None,
    duration_sec: Annotated[
        float | None, typer.Option(help="stop after this many seconds")
    ] = None,
    seed: Annotated[int, typer.Option(help="random seed")] = 0,
    start_run: Annotated[
        int, typer.Option(help="index of the first run, to replay one")
    ] = 0,
    tx_hz: Annotated[float, typer.Option(help="transmit frequency in Hz")] = 5.1e9,
    detune_hz: Annotated[
        float,
        typer.Option(
            help="set every instrument this far off the carrier it is deployed at, "
            "so the units modulate and demodulate"
        ),
    ] = 0.0,
    chosen_kinds: Annotated[
        list[str] | None,
        typer.Option(
            "--kind",
            help=f"kind of run to keep in the round, repeatable: {', '.join(_KINDS)} "
            "(default: every kind)",
        ),
    ] = None,
    span_ticks: Annotated[
        int | None,
        typer.Option(
            help="span every port's waves lie in, in 3.2 ns ticks "
            "(default: each kind's own)"
        ),
    ] = None,
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
    initialize_each_run: Annotated[
        bool,
        typer.Option(help="initialize the instruments at the start of every run"),
    ] = False,
    check_monitor: Annotated[
        bool,
        typer.Option(
            help="judge on the monitor what one port at a time sends "
            "(admin PAT; discards every instrument on the units)"
        ),
    ] = False,
    timings: Annotated[
        Path | None,
        typer.Option(help="write the units, the settings and each run's timing here"),
    ] = None,
    log_level: Annotated[str, typer.Option(help="DEBUG|INFO|WARNING|ERROR")] = "INFO",
) -> None:
    """Run the soak test on QuEL-3 units, all at once."""
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    unknown = set(chosen_kinds or ()) - set(_KINDS)
    if unknown:
        raise typer.BadParameter(
            f"{', '.join(sorted(unknown))}: not one of {', '.join(_KINDS)}",
            param_hint="--kind",
        )
    entries = [e for e in DEFAULT_ROUND if not chosen_kinds or e.kind in chosen_kinds]
    if span_ticks is not None:
        entries = [
            dataclasses.replace(
                e, profile=dataclasses.replace(e.profile, span_ticks=span_ticks)
            )
            for e in entries
        ]
    if runs is None and duration_sec is None:
        runs = rounds * len(round_order(entries))
    elif runs == 0:
        runs = None

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
                profile=entries,
                tx_hz=tx_hz,
                detune_hz=detune_hz,
                save_dir=save_dir,
                stop_on_failure=stop_on_failure,
                report_every=report_every,
                discard_instruments=discard_instruments,
                initialize_each_run=initialize_each_run,
                check_monitor=check_monitor,
                timings_path=timings,
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
