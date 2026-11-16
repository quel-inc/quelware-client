from dataclasses import replace
from typing import cast

import numpy as np
import pytest
from grpclib import GRPCError
from grpclib.const import Status
from grpclib.exceptions import StreamTerminatedError
from quelware_client.core import Session
from quelware_client.core.exceptions import RunFailedError
from quelware_client.core.instrument_driver import FixedTimelineInstrumentDriver
from quelware_core.entities.instrument import (
    FixedTimelineConfig,
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.unit import UnitLabel
from quelware_core.entities.waveform.sampled import IqWaveform

from quelware_tools.diagnostics.correctness import Judge
from quelware_tools.diagnostics.soak_test import (
    HIDDEN_AMPLITUDE,
    MARKER_TICKS,
    TICK_NS,
    RunPlan,
    SoakProfile,
    _classify,
    _draw_shown,
    _judge_monitors,
    _judge_run,
    build_directives,
    draw_plan,
)

_CONTROL = "u:tx_p04"
_READOUT = "u:trx_p00p01"
_PORTS = [_CONTROL, _READOUT]


def _info(
    port: str, alias: str, role: InstrumentRole, period_fs: int
) -> InstrumentInfo:
    return InstrumentInfo(
        id=ResourceId(f"{port}:{alias}"),
        port_id=ResourceId(port),
        definition=InstrumentDefinition(
            alias=alias,
            mode=InstrumentMode.FIXED_TIMELINE,
            role=role,
            profile=FixedTimelineProfile(4.9e9, 5.3e9),
        ),
        config=FixedTimelineConfig(
            sampling_period_fs=period_fs,
            bitdepth=16,
            samples_per_tick=4,
            timeline_step_samples=256,
        ),
    )


_EMIT_INFOS = {
    _CONTROL: _info(_CONTROL, "soak_tx_p04", InstrumentRole.TRANSMITTER, 400_000),
    _READOUT: _info(_READOUT, "soak_trx", InstrumentRole.TRANSMITTER, 800_000),
}


def test_a_run_is_drawn_again_from_its_seed() -> None:
    first = draw_plan(np.random.default_rng([7, 3]), 3, _PORTS)
    again = draw_plan(np.random.default_rng([7, 3]), 3, _PORTS)

    assert first == again


def test_waves_lie_on_the_4_tick_grid_in_order() -> None:
    for run in range(50):
        plan = draw_plan(np.random.default_rng([0, run]), run, _PORTS)
        for train in plan.waves.values():
            end_ns = 0.0
            for wave in train:
                assert round(wave.start_ns / TICK_NS) % 4 == 0
                assert round(wave.length_ns / TICK_NS) % 4 == 0
                assert wave.start_ns >= end_ns - 1e-9
                end_ns = wave.start_ns + wave.length_ns


def test_waves_and_windows_lie_within_the_span() -> None:
    span_ns = SoakProfile().span_ticks * TICK_NS
    for run in range(50):
        plan = draw_plan(
            np.random.default_rng([0, run]), run, _PORTS, capture_port_ids=[_READOUT]
        )
        spans = [
            *(w for t in plan.waves.values() for w in t),
            *(w for t in plan.windows.values() for w in t),
        ]
        assert all(w.start_ns + w.length_ns <= span_ns + 1e-9 for w in spans)


def test_the_iteration_blank_keeps_the_send_interval() -> None:
    for run in range(50):
        plan = draw_plan(np.random.default_rng([0, run]), run, _PORTS)
        assert plan.iteration_blank_ns >= 300 * TICK_NS


def test_wave_lengths_are_drawn_from_the_profile_s_kinds() -> None:
    kinds = set(SoakProfile().wave_ticks)
    for run in range(50):
        plan = draw_plan(np.random.default_rng([0, run]), run, _PORTS)
        for train in plan.waves.values():
            assert {round(w.length_ns / TICK_NS) for w in train} <= kinds


def test_capture_windows_stay_within_the_capture_budget() -> None:
    profile = SoakProfile()
    for run in range(50):
        plan = draw_plan(
            np.random.default_rng([0, run]), run, _PORTS, profile, [_READOUT]
        )
        assert set(plan.windows) == {_READOUT}
        total_ns = sum(w.length_ns for w in plan.windows[_READOUT])
        assert plan.iterations * total_ns <= profile.max_total_capture_ns


def test_only_capture_ports_get_capture_windows() -> None:
    plan = draw_plan(
        np.random.default_rng([3, 0]), 0, _PORTS, capture_port_ids=[_READOUT]
    )
    directives = build_directives(plan, _EMIT_INFOS)

    assert not directives["soak_tx_p04"].capture_windows
    assert len(directives["soak_trx"].capture_windows) == len(plan.windows[_READOUT])


def test_only_the_shown_port_carries_markers() -> None:
    plan = draw_plan(np.random.default_rng([1, 0]), 0, _PORTS)
    directives = build_directives(plan, _EMIT_INFOS)

    for port, info in _EMIT_INFOS.items():
        marker = round(MARKER_TICKS * TICK_NS * 1e6 / info.config.sampling_period_fs)
        for waveform in directives[info.definition.alias].waveform_library:
            samples = np.asarray(waveform.iq_array)
            if port == plan.shown_port:
                assert np.all(samples[:marker] == 1.0)
                assert np.allclose(samples[marker:], HIDDEN_AMPLITUDE)
            else:
                assert np.allclose(samples, HIDDEN_AMPLITUDE)


def test_every_instrument_shares_the_run_s_length() -> None:
    plan = draw_plan(np.random.default_rng([2, 0]), 0, _PORTS)
    directives = build_directives(plan, _EMIT_INFOS)

    periods = {
        info.definition.alias: info.config.sampling_period_fs
        for info in _EMIT_INFOS.values()
    }
    lengths_fs = {alias: d.length * periods[alias] for alias, d in directives.items()}
    assert len(set(lengths_fs.values())) == 1
    assert next(iter(lengths_fs.values())) >= plan.length_ns * 1e6
    assert all(d.iterations == plan.iterations for d in directives.values())


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (GRPCError(Status.INVALID_ARGUMENT, "stream 3 too short"), "refused"),
        (GRPCError(Status.UNAVAILABLE, "unit a09 not reached"), "unavailable"),
        (GRPCError(Status.INTERNAL, "boom"), "error"),
        (RunFailedError({ResourceId("u:i"): RuntimeError("past_counter")}, {}), "run"),
        (TimeoutError("still running"), "timeout"),
        (StreamTerminatedError("Connection lost"), "connection"),
        (RuntimeError("anything else"), "error"),
    ],
)
def test_a_failure_is_told_apart_by_its_kind(error: Exception, kind: str) -> None:
    assert _classify(error)[0] == kind


class _Recorder:
    """Stands in for the session and the drivers, and records what a run asks."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def initialize(self, ids) -> None:
        self.calls.append("initialize")

    async def trigger(self, ids) -> int:
        self.calls.append("trigger")
        return 0

    async def wait_for_results(self, ids, timeout_sec=None) -> dict:
        self.calls.append("wait")
        return {}

    async def apply(self, directive) -> bool:
        self.calls.append("configure")
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initialize", "first"), [(False, "configure"), (True, "initialize")]
)
async def test_a_run_initializes_first_only_when_asked(
    initialize: bool, first: str
) -> None:
    plan = draw_plan(np.random.default_rng([7, 3]), 3, _PORTS)
    directives = {a: [d] for a, d in build_directives(plan, _EMIT_INFOS).items()}
    recorder = _Recorder()
    aliases = [info.definition.alias for info in _EMIT_INFOS.values()]
    ids = [info.id for info in _EMIT_INFOS.values()]

    failure, _ = await _judge_run(
        cast(Session, recorder),
        dict.fromkeys(aliases, cast(FixedTimelineInstrumentDriver, recorder)),
        {UnitLabel("u"): aliases},
        ids,
        plan,
        directives,
        initialize=initialize,
    )

    assert failure is None
    assert recorder.calls[0] == first
    assert recorder.calls.count("initialize") == int(initialize)
    assert recorder.calls[-2:] == ["trigger", "wait"]


_MONITOR = "u:mon"
_MONITOR_INFO = _info(_MONITOR, "soak_mon", InstrumentRole.RECEIVER, 400_000)


def _checked_plan(seed: int) -> RunPlan:
    rng = np.random.default_rng([seed, 0])
    plan = draw_plan(rng, 0, _PORTS, capture_port_ids=[_MONITOR])
    ports = [ResourceId(p) for p in _PORTS]
    return replace(plan, shown_ports=_draw_shown(rng, ports))


def test_in_a_monitor_check_the_shown_port_sends_at_full_scale_the_rest_nothing():
    plan = _checked_plan(4)
    infos = {**_EMIT_INFOS, _MONITOR: _MONITOR_INFO}
    directives = build_directives(plan, infos, check=True)

    for port, info in _EMIT_INFOS.items():
        level = 1.0 if port in plan.shown_ports else 0.0
        for waveform in directives[info.definition.alias].waveform_library:
            assert np.all(np.asarray(waveform.iq_array) == level)
    assert len(directives["soak_mon"].capture_windows) == len(plan.windows[_MONITOR])


def test_one_port_of_each_unit_is_shown():
    ports = [ResourceId(p) for p in ("a:tx_p04", "a:trx_p00p01", "b:tx_p04")]
    shown = _draw_shown(np.random.default_rng(0), ports)

    assert sorted(p.split(":")[0] for p in shown) == ["a", "b"]


def _monitor_results(plan: RunPlan, gain: complex) -> dict:
    """What a monitor returns of the shown port's waves along a path of no delay."""
    period_ns = _MONITOR_INFO.config.sampling_period_fs * 1e-6
    (shown,) = plan.shown_ports
    waves = {}
    for i, w in enumerate(plan.windows[_MONITOR]):
        start = round(w.start_ns / period_ns)
        capture = np.zeros(round(w.length_ns / period_ns), dtype=complex)
        for wave in plan.waves[shown]:
            at = round(wave.start_ns / period_ns) - start
            n = round(wave.length_ns / period_ns)
            lo, hi = max(at, 0), min(at + n, len(capture))
            if lo < hi:
                turn = np.exp(1j * np.radians(wave.phase_deg))
                capture[lo:hi] = gain * wave.gain * turn
        count = plan.iterations if plan.raw else 1
        waves[f"cap{i}"] = [IqWaveform(400_000, capture.copy()) for _ in range(count)]
    return {_MONITOR_INFO.id: ResultContainer(iq_waveform_result=waves)}


def test_a_monitor_capture_of_what_the_shown_port_sent_passes():
    plan = _checked_plan(5)
    monitors = {UnitLabel("u"): _MONITOR_INFO}

    failure = _judge_monitors(Judge(), plan, monitors, _monitor_results(plan, 0.3j))

    assert failure is None


def test_a_monitor_capture_that_comes_back_weaker_is_a_wrong_run():
    # three of the shown port's waves lie whole in a window, so they measure each other
    plan = _checked_plan(9)
    results = _monitor_results(plan, 0.3j)
    for waves in results[_MONITOR_INFO.id].iq_waveform_result.values():
        waves[0].iq_array[len(waves[0].iq_array) // 2 :] *= 0.5

    failure = _judge_monitors(Judge(), plan, {UnitLabel("u"): _MONITOR_INFO}, results)

    assert failure is not None
    assert failure.kind == "wrong"


def test_a_share_of_runs_return_every_iteration_within_their_own_limit():
    profile = SoakProfile(raw_share=0.5, max_raw_capture_ns=20_000.0)
    plans = [
        draw_plan(np.random.default_rng([3, run]), run, _PORTS, profile, [_MONITOR])
        for run in range(40)
    ]

    raw = [p for p in plans if p.raw]
    assert 0 < len(raw) < len(plans)
    for plan in raw:
        assert plan.iterations in profile.raw_iterations
        total_ns = sum(w.length_ns for w in plan.windows[_MONITOR])
        assert plan.iterations * total_ns <= profile.max_raw_capture_ns


def test_no_run_is_raw_when_none_is_asked_for():
    profile = SoakProfile(raw_share=0.0)

    assert not any(
        draw_plan(np.random.default_rng([3, run]), run, _PORTS, profile).raw
        for run in range(40)
    )


def test_an_iteration_of_a_raw_run_that_came_back_empty_is_a_wrong_run():
    plan = replace(_checked_plan(9), raw=True, iterations=4)
    results = _monitor_results(plan, 0.3j)
    for waves in results[_MONITOR_INFO.id].iq_waveform_result.values():
        waves[2].iq_array[:] = 0

    failure = _judge_monitors(Judge(), plan, {UnitLabel("u"): _MONITOR_INFO}, results)

    assert failure is not None
    assert failure.kind == "wrong"
    assert "in 1 of 4 iterations (2)" in failure.detail
