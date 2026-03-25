from dataclasses import dataclass


@dataclass
class WorkerStatus:
    can_accept_tasks: bool
    is_linked_up: bool
    is_synchronized: bool


__all__ = ["WorkerStatus"]
