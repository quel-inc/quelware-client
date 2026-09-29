from grpclib import GRPCError
from grpclib.const import Status
from quelware_client.core.exceptions import RunFailedError
from quelware_core.entities.resource import ResourceId

from quelware_tools.diagnostics.trigger_wait_test import WaitResult, failure_reasons


def test_a_run_failed_on_units_is_told_apart_by_what_they_flagged() -> None:
    error = RunFailedError(
        {
            ResourceId("u:a"): RuntimeError(
                "error on unit ROUT_0: cmd_sequence_no=1 past_counter=True"
            ),
            ResourceId("u:b"): RuntimeError(
                "error on unit ROUT_1: cmd_sequence_no=1 past_counter=False"
            ),
        },
        {},
    )

    assert failure_reasons(error) == {"past_counter", "unit error"}


def test_a_run_that_broke_on_a_call_is_told_by_its_status() -> None:
    assert failure_reasons(GRPCError(Status.UNAVAILABLE, "gone")) == {"UNAVAILABLE"}
    assert failure_reasons(TimeoutError("late")) == {"TimeoutError"}


def test_the_runs_not_completed_are_the_failed_ones() -> None:
    result = WaitResult(150, runs=5, completed=3)

    assert result.failed == 2
