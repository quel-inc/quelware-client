import numpy as np
import pytest
from grpclib import GRPCError
from grpclib.const import Status
from grpclib.exceptions import StreamTerminatedError
from quelware_client.core.exceptions import RunFailedError
from quelware_core.entities.instrument import (
    FixedTimelineConfig,
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceId

from quelware_tools.diagnostics.soak_test import (
    HIDDEN_AMPLITUDE,
    MARKER_TICKS,
    TICK_NS,
    SoakProfile,
    _classify,
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
