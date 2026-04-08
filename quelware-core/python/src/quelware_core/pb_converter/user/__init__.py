import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.user import UserRole

_USER_ROLE_TO_PB = {
    UserRole.UNSPECIFIED: pb_models.UserRole.UNSPECIFIED,
    UserRole.NORMAL_USER: pb_models.UserRole.NORMAL_USER,
    UserRole.PRIVILEGED_USER: pb_models.UserRole.PRIVILEGED_USER,
    UserRole.ADMIN: pb_models.UserRole.ADMIN,
}

_USER_ROLE_FROM_PB = {v: k for k, v in _USER_ROLE_TO_PB.items()}


def user_role_to_pb(unit_status: UserRole) -> pb_models.UserRole:
    return _USER_ROLE_TO_PB[unit_status]


def user_role_from_pb(pb: pb_models.UserRole) -> UserRole:
    return _USER_ROLE_FROM_PB[pb]
