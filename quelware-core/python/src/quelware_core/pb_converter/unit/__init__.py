import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.unit import UnitStatus

_UNIT_STATUS_TO_PB = {
    UnitStatus.ACTIVE: pb_models.UnitStatus.ACTIVE,
    UnitStatus.DRAINING: pb_models.UnitStatus.DRAINING,
    UnitStatus.RELEASED: pb_models.UnitStatus.RELEASED,
    UnitStatus.UNAVAILABLE: pb_models.UnitStatus.UNAVAILABLE,
}

_UNIT_STATUS_FORM_PB = {v: k for k, v in _UNIT_STATUS_TO_PB.items()}


def unit_status_to_pb(unit_status: UnitStatus) -> pb_models.UnitStatus:
    return _UNIT_STATUS_TO_PB[unit_status]


def unit_status_from_pb(pb: pb_models.UnitStatus) -> UnitStatus:
    return _UNIT_STATUS_FORM_PB[pb]
