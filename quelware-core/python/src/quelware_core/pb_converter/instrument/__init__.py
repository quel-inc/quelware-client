import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.instrument import (
    FixedTimelineConfig,
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
    InstrumentStatus,
)
from quelware_core.entities.resource import ResourceId

_INSTRUMENT_MODE_TO_PB = {
    InstrumentMode.UNSPECIFIED: pb_models.InstrumentMode.UNSPECIFIED,
    InstrumentMode.FIXED_TIMELINE: pb_models.InstrumentMode.FIXED_TIMELINE,
}

_INSTRUMENT_MODE_FROM_PB = {v: k for k, v in _INSTRUMENT_MODE_TO_PB.items()}


def instrument_mode_to_pb(val: InstrumentMode) -> pb_models.InstrumentMode:
    return _INSTRUMENT_MODE_TO_PB[val]


def instrument_mode_from_pb(pb: pb_models.InstrumentMode) -> InstrumentMode:
    return _INSTRUMENT_MODE_FROM_PB[pb]


_INSTRUMENT_ROLE_TO_PB = {
    InstrumentRole.UNSPECIFIED: pb_models.InstrumentRole.UNSPECIFIED,
    InstrumentRole.TRANSMITTER: pb_models.InstrumentRole.TRANSMITTER,
    InstrumentRole.TRANSCEIVER: pb_models.InstrumentRole.TRANSCEIVER,
}

_INSTRUMENT_ROLE_FROM_PB = {v: k for k, v in _INSTRUMENT_ROLE_TO_PB.items()}


def instrument_role_to_pb(val: InstrumentRole) -> pb_models.InstrumentRole:
    return _INSTRUMENT_ROLE_TO_PB[val]


def instrument_role_from_pb(pb: pb_models.InstrumentRole) -> InstrumentRole:
    return _INSTRUMENT_ROLE_FROM_PB[pb]


_INSTRUMENT_STATUS_TO_PB = {
    InstrumentStatus.UNSPECIFIED: pb_models.InstrumentStatus.UNSPECIFIED,
    InstrumentStatus.UNCONFIGURED: pb_models.InstrumentStatus.UNCONFIGURED,
    InstrumentStatus.READY: pb_models.InstrumentStatus.READY,
    InstrumentStatus.RUNNING: pb_models.InstrumentStatus.RUNNING,
    InstrumentStatus.COMPLETED: pb_models.InstrumentStatus.COMPLETED,
}

_INSTRUMENT_STATUS_FROM_PB = {v: k for k, v in _INSTRUMENT_STATUS_TO_PB.items()}


def instrument_status_to_pb(val: InstrumentStatus) -> pb_models.InstrumentStatus:
    return _INSTRUMENT_STATUS_TO_PB[val]


def instrument_status_from_pb(pb: pb_models.InstrumentStatus) -> InstrumentStatus:
    return _INSTRUMENT_STATUS_FROM_PB[pb]


def instrument_definition_to_pb(
    entity: InstrumentDefinition,
) -> pb_models.InstrumentDefinition:
    pb = pb_models.InstrumentDefinition(
        alias=entity.alias,
        mode=instrument_mode_to_pb(entity.mode),
        role=instrument_role_to_pb(entity.role),
    )

    match entity.profile:
        case FixedTimelineProfile():
            pb.fixed_timeline_profile = pb_models.FixedTimelineProfile(
                frequency_range_min=entity.profile.frequency_range_min,
                frequency_range_max=entity.profile.frequency_range_max,
            )
        case _:
            raise ValueError(f"Unknown profile: {entity.profile}")

    return pb


def instrument_definition_from_pb(
    pb: pb_models.InstrumentDefinition,
) -> InstrumentDefinition:
    profile_data = None
    if pb.fixed_timeline_profile:
        profile_data = FixedTimelineProfile(
            frequency_range_min=pb.fixed_timeline_profile.frequency_range_min,
            frequency_range_max=pb.fixed_timeline_profile.frequency_range_max,
        )
    else:
        raise ValueError("Profile field is unspecified in InstrumentProfile")

    return InstrumentDefinition(
        alias=pb.alias,
        mode=instrument_mode_from_pb(pb.mode),
        role=instrument_role_from_pb(pb.role),
        profile=profile_data,
    )


def instrument_to_pb(entity: InstrumentInfo) -> pb_models.Instrument:
    pb = pb_models.Instrument(
        id=str(entity.id),
        port_id=str(entity.port_id),
        definition=instrument_definition_to_pb(entity.definition),
    )
    match entity.config:
        case FixedTimelineConfig():
            pb.fixed_timeline_config = pb_models.FixedTimelineConfig(
                sampling_period_fs=entity.config.sampling_period_fs,
                bitdepth=entity.config.bitdepth,
            )
        case _:
            raise ValueError(f"Unknown config: {entity.config}")
    return pb


def instrument_from_pb(pb: pb_models.Instrument) -> InstrumentInfo:
    if pb.definition is None:
        raise ValueError("Profile field is unspecified in Instrument")
    config = None
    if pb.fixed_timeline_config:
        config = FixedTimelineConfig(
            sampling_period_fs=pb.fixed_timeline_config.sampling_period_fs,
            bitdepth=pb.fixed_timeline_config.bitdepth,
        )
    else:
        raise ValueError("Config field is unspecified in InstrumentProfile")
    return InstrumentInfo(
        id=ResourceId(pb.id),
        port_id=ResourceId(pb.port_id),
        definition=instrument_definition_from_pb(pb.definition),
        config=config,
    )
