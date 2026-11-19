"""quel-soak-compare: compare the timings of two quel-soak-test runs.

Reads two files written by ``quel-soak-test --timings``, A and B, and prints, as
Markdown tables, how long each step took in each: the median, the 95th percentile
and the longest, over the runs that completed. When both drew the same runs (the
same seed, kinds and ports), it also prints the median of each run's difference,
B minus A, which cancels out how heavy each run is. A and B are named after their
files unless labelled.
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
        "| step (ms) | A median | B median | A p95 | B p95 | A max | B max"
        + (" | median of B - A |" if paired else " |"),
        "|---" * (7 + paired) + "|",
    ]
    for s in steps:
        row = [
            s.step,
            *(
                _ms(x)
                for x in (
                    s.a_median,
                    s.b_median,
                    s.a_p95,
                    s.b_p95,
                    s.a_max,
                    s.b_max,
                )
            ),
        ]
        if paired:
            diff = s.paired_median_diff
            row.append("" if diff is None else f"{diff * 1e3:+.0f}")
        lines.append("| " + " | ".join(row) + " |")
    return lines


def format_comparison(c: SoakComparison, label_a: str = "", label_b: str = "") -> str:
    """The comparison as a line for each of A and B and Markdown tables, in
    milliseconds: one over every run, and one for each kind of run when there are
    several."""
    lines = [
        f"A: {label_a + ' - ' if label_a else ''}{c.a_runs} runs, "
        f"{c.a_failed} failed, {c.a_duration_sec:.0f} s",
        f"B: {label_b + ' - ' if label_b else ''}{c.b_runs} runs, "
        f"{c.b_failed} failed, {c.b_duration_sec:.0f} s",
        "runs compared one by one"
        if c.paired
        else "runs drawn differently: only the spread is compared",
        "",
        *_table(c.steps, c.paired),
    ]
    for side, only in (("A", c.kinds_only_in_a), ("B", c.kinds_only_in_b)):
        if only:
            lines += ["", f"only in {side}: {', '.join(only)}"]
    for kind, steps in c.by_kind.items():
        if steps:
            lines += ["", f"{kind}:", "", *_table(steps, c.paired)]
        else:
            lines += ["", f"{kind}: no run of it completed in both"]
    return "\n".join(lines)


def _entry(
    a: Annotated[Path, typer.Argument(help="timings file A")],
    b: Annotated[Path, typer.Argument(help="timings file B, compared against A")],
    label_a: Annotated[
        str | None, typer.Option(help="name for A (default: its file name)")
    ] = None,
    label_b: Annotated[
        str | None, typer.Option(help="name for B (default: its file name)")
    ] = None,
) -> None:
    """Compare the timings of two quel-soak-test runs."""
    try:
        comparison = compare_soak_timings(load_timings(a), load_timings(b))
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(format_comparison(comparison, label_a or a.name, label_b or b.name))


def cli() -> None:
    typer.run(_entry)


if __name__ == "__main__":
    cli()
