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
    old_median: float
    new_median: float
    old_p95: float
    new_p95: float
    old_max: float
    new_max: float
    # the median over the runs completed in both of new minus old; None unless paired
    paired_median_diff: float | None


@dataclass(frozen=True)
class SoakComparison:
    # whether both drew the same runs, so that each run is compared with itself
    paired: bool
    old_runs: int
    new_runs: int
    old_failed: int
    new_failed: int
    old_duration_sec: float
    new_duration_sec: float
    steps: list[StepComparison]


def load_timings(path: Path) -> dict[str, Any]:
    """A timings file, refused when it is laid out otherwise than this reads."""
    content = json.loads(path.read_text())
    if content.get("format") != TIMINGS_FORMAT:
        raise ValueError(
            f"{path} is in timings format {content.get('format')}, not {TIMINGS_FORMAT}"
        )
    return content


def _plan(run: Mapping[str, Any]) -> tuple[Any, ...]:
    return run["waves"], run["iterations"], run["raw"]


def _same_runs(old: Mapping[str, Any], new: Mapping[str, Any]) -> bool:
    if old["settings"] != new["settings"] or old["ports"] != new["ports"]:
        return False
    old_runs = {r["run"]: r for r in old["runs"]}
    common = [r for r in new["runs"] if r["run"] in old_runs]
    return bool(common) and all(_plan(r) == _plan(old_runs[r["run"]]) for r in common)


def _seconds(run: Mapping[str, Any], step: str) -> float | None:
    steps = run["steps"]
    return sum(steps.values()) if step == TOTAL else steps.get(step)


def compare_soak_timings(
    old: Mapping[str, Any], new: Mapping[str, Any]
) -> SoakComparison:
    """How long each step of ``new``'s runs took against ``old``'s."""
    paired = _same_runs(old, new)
    old_done = {r["run"]: r for r in old["runs"] if r["failure"] is None}
    new_done = {r["run"]: r for r in new["runs"] if r["failure"] is None}
    both = sorted(old_done.keys() & new_done.keys())
    present = [s for s in _STEPS if any(s in r["steps"] for r in old["runs"])]
    steps = []
    for step in [*present, TOTAL]:
        o = [x for r in old_done.values() if (x := _seconds(r, step)) is not None]
        n = [x for r in new_done.values() if (x := _seconds(r, step)) is not None]
        if not o or not n:
            continue
        diffs = [
            b - a
            for i in both
            if (a := _seconds(old_done[i], step)) is not None
            and (b := _seconds(new_done[i], step)) is not None
        ]
        steps.append(
            StepComparison(
                step=step,
                old_median=float(np.median(o)),
                new_median=float(np.median(n)),
                old_p95=float(np.percentile(o, 95)),
                new_p95=float(np.percentile(n, 95)),
                old_max=max(o),
                new_max=max(n),
                paired_median_diff=(
                    float(np.median(diffs)) if paired and diffs else None
                ),
            )
        )
    return SoakComparison(
        paired=paired,
        old_runs=len(old["runs"]),
        new_runs=len(new["runs"]),
        old_failed=sum(r["failure"] is not None for r in old["runs"]),
        new_failed=sum(r["failure"] is not None for r in new["runs"]),
        old_duration_sec=old["finished_at"] - old["started_at"],
        new_duration_sec=new["finished_at"] - new["started_at"],
        steps=steps,
    )


__all__ = [
    "TOTAL",
    "SoakComparison",
    "StepComparison",
    "compare_soak_timings",
    "load_timings",
]
