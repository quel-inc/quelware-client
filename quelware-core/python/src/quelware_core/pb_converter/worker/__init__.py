import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.worker import WorkerStatus


def worker_status_to_pb(worker_status: WorkerStatus) -> pb_models.WorkerStatus:
    return pb_models.WorkerStatus(
        can_accept_tasks=worker_status.can_accept_tasks,
        is_linked_up=worker_status.is_linked_up,
        is_synchronized=worker_status.is_synchronized,
    )


def worker_status_from_pb(pb: pb_models.WorkerStatus) -> WorkerStatus:
    return WorkerStatus(
        can_accept_tasks=pb.can_accept_tasks,
        is_linked_up=pb.is_linked_up,
        is_synchronized=pb.is_synchronized,
    )
