"""quel-soak-compare: compare the timings of two quel-soak-test runs.

Reads two files written by ``quel-soak-test --timings`` and prints, as a Markdown
table, how long each step took in the new against the old: the median, the 95th
percentile and the longest, over the runs that completed. When both drew the same
runs (the same seed, settings and ports), it also prints the median of each run's
difference, which cancels out how heavy each run is.
"""

from pathlib import Path
from typing import Annotated

import typer

from quelware_tools.diagnostics.soak_compare import (
    SoakComparison,
    StepComparison,
    compare_soak_timings,
    load_timings,
)


def _ms(sec: float) -> str:
    return f"{sec * 1e3:.0f}"


def _table(steps: list[StepComparison], paired: bool) -> list[str]:
    lines = [
        "| step (ms) | old median | new median | old p95 | new p95 | old max | new max"
        + (" | median of new - old |" if paired else " |"),
        "|---" * (7 + paired) + "|",
    ]
    for s in steps:
        row = [
            s.step,
            *(
                _ms(x)
                for x in (
                    s.old_median,
                    s.new_median,
                    s.old_p95,
                    s.new_p95,
                    s.old_max,
                    s.new_max,
                )
            ),
        ]
        if paired:
            diff = s.paired_median_diff
            row.append("" if diff is None else f"{diff * 1e3:+.0f}")
        lines.append("| " + " | ".join(row) + " |")
    return lines


def format_comparison(c: SoakComparison) -> str:
    """The comparison as a few lines and Markdown tables, in milliseconds: one over
    every run, and one for each kind of run when there are several."""
    lines = [
        f"old: {c.old_runs} runs, {c.old_failed} failed, {c.old_duration_sec:.0f} s",
        f"new: {c.new_runs} runs, {c.new_failed} failed, {c.new_duration_sec:.0f} s",
        "runs compared one by one"
        if c.paired
        else "runs drawn differently: only the spread is compared",
        "",
        *_table(c.steps, c.paired),
    ]
    for kind, steps in c.by_kind.items():
        if steps:
            lines += ["", f"{kind}:", "", *_table(steps, c.paired)]
        else:
            lines += ["", f"{kind}: no run of it completed in both"]
    return "\n".join(lines)


def _entry(
    old: Annotated[Path, typer.Argument(help="timings file to compare against")],
    new: Annotated[Path, typer.Argument(help="timings file to compare")],
) -> None:
    """Compare the timings of two quel-soak-test runs."""
    try:
        comparison = compare_soak_timings(load_timings(old), load_timings(new))
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(format_comparison(comparison))


def cli() -> None:
    typer.run(_entry)


if __name__ == "__main__":
    cli()
