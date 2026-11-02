from dataclasses import replace

from grpclib import GRPCError
from grpclib.const import Status
from quelware_core.entities.instrument import (
    FixedTimelineConfig,
    InstrumentInfo,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceId

from quelware_tools.diagnostics.recover_past_counter import (
    Want,
    definition,
    plans_for,
    report_of,
    split_hz,
)

_TX, _RX = InstrumentRole.TRANSMITTER, InstrumentRole.RECEIVER


def test_a_port_is_tried_by_the_prefix_of_its_name_most_streams_first() -> None:
    assert plans_for("trx_p00p01")[0] == [
        Want(_TX, -1),
        Want(_TX, 1),
        Want(_RX, -1),
        Want(_RX, 1),
    ]
    assert plans_for("tx_p02") == [[Want(_TX, -1), Want(_TX, 1)], [Want(_TX, 0)]]
    assert plans_for("rx_p05") == [[Want(_RX, -1), Want(_RX, 1)], [Want(_RX, 0)]]


def test_a_port_whose_name_says_no_role_is_skipped() -> None:
    assert plans_for("monitor") == []


def test_two_instruments_are_set_apart_by_more_than_a_stream_s_effective_band() -> None:
    period_fs = 400_000  # a 2.5 GHz stream, 2.0 GHz of it usable
    split = split_hz(period_fs)
    low = definition("tx_p02", Want(_TX, -1), 5.1e9, split).profile
    high = definition("tx_p02", Want(_TX, 1), 5.1e9, split).profile

    span = high.frequency_range_max - low.frequency_range_min
    assert span > 0.8 * 1e15 / period_fs
    assert (low.frequency_range_min + high.frequency_range_max) / 2 == 5.1e9


def _info(rid: str, alias: str) -> InstrumentInfo:
    return InstrumentInfo(
        id=ResourceId(rid),
        port_id=ResourceId("u:tx_p02"),
        definition=replace(definition("tx_p02", Want(_TX, 0), 5.1e9, 0.0), alias=alias),
        config=FixedTimelineConfig(
            sampling_period_fs=400_000,
            bitdepth=16,
            timeline_step_samples=64,
            samples_per_tick=8,
        ),
    )


def test_a_run_is_cancelled_late_or_failed_by_how_it_ended() -> None:
    infos = [_info("u:a", "a"), _info("u:b", "b"), _info("u:c", "c")]
    failures = {
        ResourceId("u:a"): GRPCError(Status.ABORTED, "execution aborted"),
        ResourceId("u:c"): RuntimeError("error on unit ROUT_0: fifo_underflow"),
    }

    report = report_of(["u"], 1, infos, failures)

    assert report.cancelled == 1
    assert report.late == ("b",)
    assert set(report.failed) == {"c"}
    assert not report.ok


def test_every_run_cancelled_is_ok() -> None:
    infos = [_info("u:a", "a")]
    failures = {ResourceId("u:a"): GRPCError(Status.ABORTED, "execution aborted")}

    assert report_of(["u"], 1, infos, failures).ok
