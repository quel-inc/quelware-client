import json
from pathlib import Path

import pytest

from quelware_tools.cli.soak_compare import format_comparison
from quelware_tools.diagnostics.soak_compare import (
    TOTAL,
    compare_soak_timings,
    load_timings,
)
from quelware_tools.diagnostics.soak_test import TIMINGS_FORMAT


def _run(run: int, configure: float, wait: float, failure: str | None = None) -> dict:
    return {
        "run": run,
        "started_at": float(run),
        "steps": {"configure": configure, "trigger": 0.3, "wait": wait},
        "waves": 10 + run,
        "iterations": 100,
        "raw": False,
        "failure": failure,
    }


def _timings(runs: list[dict], seed: int = 0) -> dict:
    return {
        "format": TIMINGS_FORMAT,
        "units": ["u"],
        "ports": ["u:tx_p00"],
        "settings": {"seed": seed},
        "versions": {},
        "started_at": 0.0,
        "finished_at": 10.0,
        "runs": runs,
    }


def _step(comparison, name):
    return next(s for s in comparison.steps if s.step == name)


def test_runs_drawn_alike_are_compared_one_by_one() -> None:
    old = _timings([_run(0, 2.0, 0.1), _run(1, 3.0, 0.9)])
    new = _timings([_run(0, 0.2, 0.2), _run(1, 0.4, 1.0)])

    c = compare_soak_timings(old, new)

    assert c.paired
    assert _step(c, "configure").paired_median_diff == pytest.approx(-2.2)
    assert _step(c, "wait").paired_median_diff == pytest.approx(0.1)
    assert _step(c, TOTAL).old_max == pytest.approx(3.0 + 0.3 + 0.9)


def test_runs_drawn_from_another_seed_are_compared_only_by_their_spread() -> None:
    old = _timings([_run(0, 2.0, 0.1)], seed=0)
    new = _timings([_run(0, 0.2, 0.2)], seed=1)

    c = compare_soak_timings(old, new)

    assert not c.paired
    assert all(s.paired_median_diff is None for s in c.steps)
    assert _step(c, "configure").new_median == pytest.approx(0.2)


def test_failed_runs_are_counted_but_not_timed() -> None:
    old = _timings([_run(0, 2.0, 0.1), _run(1, 9.0, 9.0, failure="run")])
    new = _timings([_run(0, 0.2, 0.2), _run(1, 0.3, 0.3)])

    c = compare_soak_timings(old, new)

    assert (c.old_failed, c.new_failed) == (1, 0)
    assert _step(c, "configure").old_max == pytest.approx(2.0)
    assert _step(c, "configure").paired_median_diff == pytest.approx(-1.8)


def test_a_file_in_another_format_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    path.write_text(json.dumps(_timings([]) | {"format": TIMINGS_FORMAT + 1}))

    with pytest.raises(ValueError, match="format"):
        load_timings(path)


def test_the_table_has_a_difference_column_only_when_runs_are_paired() -> None:
    old = _timings([_run(0, 2.0, 0.1)])
    paired = format_comparison(compare_soak_timings(old, _timings([_run(0, 0.2, 0.2)])))
    unpaired = format_comparison(
        compare_soak_timings(old, _timings([_run(0, 0.2, 0.2)], seed=1))
    )

    assert "| configure | 2000 | 200 |" in paired
    assert paired.splitlines()[-1].endswith("|")
    assert "new - old" in paired
    assert "new - old" not in unpaired
