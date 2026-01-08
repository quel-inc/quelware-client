import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.port import PortRole

_PORT_ROLE_TO_PB = {
    PortRole.UNSPECIFIED: pb_models.PortRole.UNSPECIFIED,
    PortRole.TRANSMITTER: pb_models.PortRole.TRANSMITTER,
    PortRole.TRANSCEIVER: pb_models.PortRole.TRANSCEIVER,
}

_PORT_ROLE_FROM_PB = {v: k for k, v in _PORT_ROLE_TO_PB.items()}


def port_role_to_pb(val: PortRole) -> pb_models.PortRole:
    return _PORT_ROLE_TO_PB[val]


def port_role_from_pb(pb: pb_models.PortRole) -> PortRole:
    return _PORT_ROLE_FROM_PB[pb]
