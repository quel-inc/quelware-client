import math
from typing import Protocol


class TriggerCountProposer(Protocol):
    def propose_count(
        self, current_time: int, reference_time: int, min_wait_count: int
    ) -> int: ...


class FixedOffsetTriggerCountProposer(TriggerCountProposer):
    def __init__(self, grid_step: int, offset: int):
        self._grid_step = grid_step
        self._offset = offset

    def propose_count(
        self, current_time: int, reference_time: int, min_wait_count: int
    ) -> int:
        earliest_allowed = current_time + min_wait_count
        target_relative = earliest_allowed - (reference_time + self._offset)
        n = math.ceil(target_relative / self._grid_step)
        proposed_time = reference_time + (n * self._grid_step) + self._offset
        return proposed_time


__init__ = ["TriggerCountProposer", "FixedOffsetTriggerCountProposer"]
