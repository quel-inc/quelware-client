"""Compare the timings of two soak tests, as ``run_soak_test(timings_path=...)`` writes
them.

When both drew the same runs, each run is compared with itself; otherwise only the
spread of each step is."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .soak_test import TIMINGS_FORMAT

_STEPS = ("initialize", "configure", "trigger", "wait")
TOTAL = "total"


@dataclass(frozen=True)
class StepComparison:
    step: str
    # over the runs that completed, in seconds
    a_median: float
    b_median: float
    a_p95: float
    b_p95: float
    a_max: float
    b_max: float
    # the median over the runs completed in both of B minus A; None unless paired
    paired_median_diff: float | None


@dataclass(frozen=True)
class SoakComparison:
    # whether both drew the same runs, so that each run is compared with itself
    paired: bool
    a_runs: int
    b_runs: int
    a_failed: int
    b_failed: int
    a_duration_sec: float
    b_duration_sec: float
    steps: list[StepComparison]
    # the same over the runs of each kind drawn in both; empty when both ran one kind
    by_kind: dict[str, list[StepComparison]]
    kinds_only_in_a: list[str]
    kinds_only_in_b: list[str]


def load_timings(path: Path) -> dict[str, Any]:
    """A timings file, refused when it is laid out otherwise than this reads."""
    content = json.loads(path.read_text())
    if content.get("format") != TIMINGS_FORMAT:
        raise ValueError(
            f"{path} is in timings format {content.get('format')}, not {TIMINGS_FORMAT}"
        )
    return content


# the settings that shape which runs are drawn; others, such as the frequency, do not
_DRAW_SETTINGS = ("seed", "profile", "check_monitor")


def _plan(run: Mapping[str, Any]) -> tuple[Any, ...]:
    return run["kind"], run["waves"], run["iterations"], run["raw"]


def _same_runs(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    if a["ports"] != b["ports"] or any(
        a["settings"].get(k) != b["settings"].get(k) for k in _DRAW_SETTINGS
    ):
        return False
    a_runs = {r["run"]: r for r in a["runs"]}
    common = [r for r in b["runs"] if r["run"] in a_runs]
    return bool(common) and all(_plan(r) == _plan(a_runs[r["run"]]) for r in common)


def _seconds(run: Mapping[str, Any], step: str) -> float | None:
    steps = run["steps"]
    return sum(steps.values()) if step == TOTAL else steps.get(step)


def _compare_steps(
    a_runs: list[Mapping[str, Any]],
    b_runs: list[Mapping[str, Any]],
    paired: bool,
) -> list[StepComparison]:
    a_done = {r["run"]: r for r in a_runs if r["failure"] is None}
    b_done = {r["run"]: r for r in b_runs if r["failure"] is None}
    both = sorted(a_done.keys() & b_done.keys())
    present = [s for s in _STEPS if any(s in r["steps"] for r in [*a_runs, *b_runs])]
    steps = []
    for step in [*present, TOTAL]:
        a_secs = [x for r in a_done.values() if (x := _seconds(r, step)) is not None]
        b_secs = [x for r in b_done.values() if (x := _seconds(r, step)) is not None]
        if not a_secs or not b_secs:
            continue
        diffs = [
            b - a
            for i in both
            if (a := _seconds(a_done[i], step)) is not None
            and (b := _seconds(b_done[i], step)) is not None
        ]
        steps.append(
            StepComparison(
                step=step,
                a_median=float(np.median(a_secs)),
                b_median=float(np.median(b_secs)),
                a_p95=float(np.percentile(a_secs, 95)),
                b_p95=float(np.percentile(b_secs, 95)),
                a_max=max(a_secs),
                b_max=max(b_secs),
                paired_median_diff=(
                    float(np.median(diffs)) if paired and diffs else None
                ),
            )
        )
    return steps


def _by_kind(runs: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    kinds: dict[str, list[Mapping[str, Any]]] = {}
    for r in runs:
        kinds.setdefault(r["kind"], []).append(r)
    return kinds


def compare_soak_timings(a: Mapping[str, Any], b: Mapping[str, Any]) -> SoakComparison:
    """How long each step of ``b``'s runs took against ``a``'s, over all runs and over
    the runs of each kind."""
    paired = _same_runs(a, b)
    a_kinds = _by_kind(a["runs"])
    b_kinds = _by_kind(b["runs"])
    kinds = [k for k in a_kinds if k in b_kinds]
    several = len(a_kinds) > 1 or len(b_kinds) > 1 or a_kinds.keys() != b_kinds.keys()
    return SoakComparison(
        paired=paired,
        a_runs=len(a["runs"]),
        b_runs=len(b["runs"]),
        a_failed=sum(r["failure"] is not None for r in a["runs"]),
        b_failed=sum(r["failure"] is not None for r in b["runs"]),
        a_duration_sec=a["finished_at"] - a["started_at"],
        b_duration_sec=b["finished_at"] - b["started_at"],
        steps=_compare_steps(a["runs"], b["runs"], paired),
        by_kind=(
            {k: _compare_steps(a_kinds[k], b_kinds[k], paired) for k in kinds}
            if several
            else {}
        ),
        kinds_only_in_a=[k for k in a_kinds if k not in b_kinds],
        kinds_only_in_b=[k for k in b_kinds if k not in a_kinds],
    )


__all__ = [
    "TOTAL",
    "SoakComparison",
    "StepComparison",
    "compare_soak_timings",
    "load_timings",
]
