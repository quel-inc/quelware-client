import json
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

from quelware_tools.diagnostics.correctness import Judge, Record, delay_shot
from quelware_tools.diagnostics.soak_test import (
    DEFAULT_KINDS,
    DENSE_CR_PROFILE,
    HIDDEN_AMPLITUDE,
    MARKER_TICKS,
    PACKED_RB_PROFILE,
    PACKED_SWEEP_PROFILE,
    SPECTROSCOPY_PROFILE,
    TICK_NS,
    TIMINGS_FORMAT,
    RunPlan,
    RunTiming,
    SoakProfile,
    SoakReport,
    _classify,
    _draw_shown,
    _judge_monitors,
    _judge_run,
    _write_timings,
    build_directives,
    draw_plan,
    draw_run,
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


def test_a_packed_rb_run_sends_tens_of_thousands_of_events_from_a_small_library():
    profile = PACKED_RB_PROFILE
    plan = draw_plan(np.random.default_rng([0, 0]), 0, _PORTS, profile, [_READOUT])
    directives = build_directives(plan, _EMIT_INFOS)

    for port, info in _EMIT_INFOS.items():
        directive = directives[info.definition.alias]
        assert len(plan.waves[port]) > 50_000
        assert len(directive.events) == len(plan.waves[port])
        assert len(directive.waveform_library) <= len(profile.wave_ticks)
    total_ns = sum(w.length_ns for w in plan.windows[_READOUT])
    assert plan.iterations * total_ns <= profile.max_total_capture_ns


@pytest.mark.parametrize("profile", [PACKED_RB_PROFILE, PACKED_SWEEP_PROFILE])
def test_each_packed_job_sends_its_waves_then_its_readout_then_a_blank(profile):
    plan = draw_plan(np.random.default_rng([1, 0]), 0, _PORTS, profile, [_READOUT])
    job_ns = (profile.span_ticks + profile.readout_ticks + profile.job_blank_ticks) * (
        TICK_NS
    )

    for train in plan.waves.values():
        end_ns = 0.0
        for wave in train:
            offset_ns = wave.start_ns % job_ns
            assert offset_ns + wave.length_ns <= profile.span_ticks * TICK_NS + 1e-6
            assert round(wave.start_ns / TICK_NS) % 4 == 0
            assert wave.start_ns >= end_ns - 1e-6
            end_ns = wave.start_ns + wave.length_ns
    for k, window in enumerate(plan.windows[_READOUT]):
        assert window.start_ns == pytest.approx(
            k * job_ns + profile.span_ticks * TICK_NS
        )
        assert window.length_ns == pytest.approx(profile.readout_ticks * TICK_NS)
    assert plan.length_ns == pytest.approx(
        profile.jobs * job_ns - profile.job_blank_ticks * TICK_NS
    )


def test_a_dense_cr_run_sends_a_few_long_flat_pulses() -> None:
    plan = draw_plan(np.random.default_rng([0, 0]), 0, _PORTS, DENSE_CR_PROFILE)
    directive = build_directives(plan, _EMIT_INFOS)["soak_tx_p04"]

    library_samples = sum(len(w.iq_array) for w in directive.waveform_library)
    assert library_samples > 2000
    assert len(directive.events) < 10


def test_a_spectroscopy_run_captures_long_windows_with_a_short_blank() -> None:
    plans = [
        draw_plan(
            np.random.default_rng([0, run]),
            run,
            _PORTS,
            SPECTROSCOPY_PROFILE,
            [_READOUT],
        )
        for run in range(20)
    ]

    assert max(w.length_ns for p in plans for w in p.windows[_READOUT]) > 4000
    assert all(p.iteration_blank_ns == 1024.0 for p in plans)


def test_each_kind_is_drawn_about_as_often_and_again_from_its_seed() -> None:
    kinds = {"long": SoakProfile(), "short": SoakProfile(span_ticks=400)}
    plans = [
        draw_run(np.random.default_rng([0, run]), run, _PORTS, kinds)
        for run in range(400)
    ]
    again = draw_run(np.random.default_rng([0, 7]), 7, _PORTS, kinds)

    assert 140 < sum(p.kind == "long" for p in plans) < 260
    assert again == plans[7]


def test_every_default_kind_draws_a_run() -> None:
    for kind, profile in DEFAULT_KINDS.items():
        plan = draw_plan(np.random.default_rng([0, 0]), 0, _PORTS, profile)
        assert all(plan.waves.values()), kind


def test_a_run_drawn_from_one_profile_is_drawn_as_before() -> None:
    drawn = draw_run(np.random.default_rng([5, 2]), 2, _PORTS, SoakProfile())
    planned = draw_plan(np.random.default_rng([5, 2]), 2, _PORTS, SoakProfile())

    assert drawn == planned
    assert drawn.kind == ""


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

    failure, _, laps = await _judge_run(
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
    assert list(laps) == list(dict.fromkeys(recorder.calls))


class _TriggerFails(_Recorder):
    async def trigger(self, ids) -> int:
        self.calls.append("trigger")
        raise GRPCError(Status.UNAVAILABLE, "unit u not reached")


@pytest.mark.asyncio
async def test_a_failed_run_is_timed_up_to_the_step_it_failed_in() -> None:
    plan = draw_plan(np.random.default_rng([7, 3]), 3, _PORTS)
    directives = {a: [d] for a, d in build_directives(plan, _EMIT_INFOS).items()}
    recorder = _TriggerFails()
    aliases = [info.definition.alias for info in _EMIT_INFOS.values()]

    failure, _, laps = await _judge_run(
        cast(Session, recorder),
        dict.fromkeys(aliases, cast(FixedTimelineInstrumentDriver, recorder)),
        {UnitLabel("u"): aliases},
        [info.id for info in _EMIT_INFOS.values()],
        plan,
        directives,
    )

    assert failure is not None and failure.kind == "unavailable"
    assert list(laps) == ["configure", "trigger"]


def test_the_timings_name_the_units_ports_versions_and_every_run(tmp_path) -> None:
    report = SoakReport(["a28", "a29"], runs=2, completed=1)
    report.timings += [
        RunTiming(
            0,
            "sparse",
            1.0,
            {"configure": 0.4, "trigger": 0.7, "wait": 0.4},
            12,
            100,
            False,
            None,
        ),
        RunTiming(
            1,
            "pulse-train",
            3.0,
            {"configure": 0.5, "trigger": 0.8},
            9,
            10,
            True,
            "timeout",
        ),
    ]
    path = tmp_path / "out" / "timings.json"

    _write_timings(path, report, [ResourceId(p) for p in _PORTS], {"seed": 5}, 0.5)

    content = json.loads(path.read_text())
    assert content["format"] == TIMINGS_FORMAT
    assert content["units"] == ["a28", "a29"]
    assert content["ports"] == _PORTS
    assert content["settings"] == {"seed": 5}
    assert set(content["versions"]) == {"quelware-tools", "quelware-client"}
    assert content["started_at"] == 0.5
    assert [r["run"] for r in content["runs"]] == [0, 1]
    assert content["runs"][1]["steps"] == {"configure": 0.5, "trigger": 0.8}
    assert content["runs"][1]["failure"] == "timeout"


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


def _judge_measured(plan: RunPlan, gain: complex) -> Judge:
    """A judge that has measured the delay of the shown port's path, of no delay."""
    (shown,) = plan.shown_ports
    shot = delay_shot(shown)
    (pulse,) = shot.pulses
    (window,) = shot.windows
    period_ns = _MONITOR_INFO.config.sampling_period_fs * 1e-6
    capture = np.zeros(round(window.length_ns / period_ns), dtype=complex)
    at = round(pulse.start_ns / period_ns)
    capture[at : at + round(pulse.shape.length_ns / period_ns)] = gain * pulse.gain
    judge = Judge()
    assert (
        judge.check(
            Record(str(_MONITOR_INFO.id), period_ns, shot, {window.name: capture})
        )
        == []
    )
    return judge


def test_a_monitor_capture_of_what_the_shown_port_sent_passes():
    plan = _checked_plan(5)
    monitors = {UnitLabel("u"): _MONITOR_INFO}

    judge = _judge_measured(plan, 0.3j)

    failure = _judge_monitors(judge, plan, monitors, _monitor_results(plan, 0.3j))

    assert failure is None


def test_a_monitor_capture_that_comes_back_weaker_is_a_wrong_run():
    # three of the shown port's waves lie whole in a window, so they measure each other
    plan = _checked_plan(9)
    results = _monitor_results(plan, 0.3j)
    for waves in results[_MONITOR_INFO.id].iq_waveform_result.values():
        waves[0].iq_array[len(waves[0].iq_array) // 2 :] *= 0.5

    failure = _judge_monitors(
        _judge_measured(plan, 0.3j), plan, {UnitLabel("u"): _MONITOR_INFO}, results
    )

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

    failure = _judge_monitors(
        _judge_measured(plan, 0.3j), plan, {UnitLabel("u"): _MONITOR_INFO}, results
    )

    assert failure is not None
    assert failure.kind == "wrong"
    assert "in 1 of 4 iterations (2)" in failure.detail


def test_a_monitor_capture_from_a_port_whose_delay_was_not_measured_is_a_wrong_run():
    plan = _checked_plan(5)

    failure = _judge_monitors(
        Judge(), plan, {UnitLabel("u"): _MONITOR_INFO}, _monitor_results(plan, 0.3j)
    )

    assert failure is not None
    assert "no delay was measured" in failure.detail
