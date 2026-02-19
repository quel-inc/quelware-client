import pytest
from quelware_core.entities import directives
from quelware_core.entities.instrument import (
    FixedTimelineConfig,
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import Session
from quelware_client.core._agent_container import AgentContainer
from quelware_client.core.instrument_driver import (
    InstrumentDriver,
    create_instrument_driver_fixed_timeline,
)
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock


def _create_inst_driver():
    inst_agent = InstrumentAgentMock()
    inst_driver = InstrumentDriver(
        SessionToken("token"),
        ResourceId("unit-a:i1"),
        ResourceId("unit-a:p1"),
        InstrumentDefinition(
            alias="alias",
            mode=InstrumentMode.FIXED_TIMELINE,
            role=InstrumentRole.TRANSCEIVER,
            profile=FixedTimelineProfile(
                frequency_range_min=5_000_000_000, frequency_range_max=5_100_000_000
            ),
        ),
        FixedTimelineConfig(sampling_period_fs=400_000, bitdepth=16),
        inst_agent,
    )
    return inst_driver


@pytest.mark.asyncio
async def test_apply():
    inst_driver = _create_inst_driver()

    ds = [directives.SetFrequency(60_000_000), directives.SetPhaseOffset(120)]
    for d in ds:
        await inst_driver.apply(d)


def test_create_instrument_driver_fixed_timeline():
    agent_container = AgentContainer()
    agent_container.update_instrument_agent(UnitLabel("unit-a"), InstrumentAgentMock())
    session = Session(
        resource_ids=[ResourceId("unit-a:i1"), ResourceId("unit-a:i2")],
        agent=agent_container,
        token=SessionToken("token"),
    )

    instrument_info = InstrumentInfo(
        id=ResourceId("unit-a:i1"),
        port_id=ResourceId("unit-a:p1"),
        definition=InstrumentDefinition(
            alias="alias",
            mode=InstrumentMode.FIXED_TIMELINE,
            role=InstrumentRole.TRANSCEIVER,
            profile=FixedTimelineProfile(
                frequency_range_min=5_000_000_000, frequency_range_max=5_100_000_000
            ),
        ),
        config=FixedTimelineConfig(sampling_period_fs=400_000, bitdepth=16),
    )
    create_instrument_driver_fixed_timeline(session, instrument_info)


def test_create_instrument_driver_fixed_timeline_with_invalid_id_raises_error():
    agent_container = AgentContainer()
    agent_container.update_instrument_agent(UnitLabel("unit-a"), InstrumentAgentMock())
    session = Session(
        resource_ids=[ResourceId("unit-a:i1"), ResourceId("unit-a:i2")],
        agent=agent_container,
        token=SessionToken("token"),
    )

    instrument_info = InstrumentInfo(
        id=ResourceId("invalid_id"),
        port_id=ResourceId("unit-a:p1"),
        definition=InstrumentDefinition(
            alias="alias",
            mode=InstrumentMode.FIXED_TIMELINE,
            role=InstrumentRole.TRANSCEIVER,
            profile=FixedTimelineProfile(
                frequency_range_min=5_000_000_000, frequency_range_max=5_100_000_000
            ),
        ),
        config=FixedTimelineConfig(sampling_period_fs=400_000, bitdepth=16),
    )

    with pytest.raises(ValueError):
        create_instrument_driver_fixed_timeline(session, instrument_info)


def test_create_instrument_driver_fixed_timeline_with_mismatched_mode_raises_error():
    agent_container = AgentContainer()
    agent_container.update_instrument_agent(UnitLabel("unit-a"), InstrumentAgentMock())
    session = Session(
        resource_ids=[ResourceId("unit-a:i1"), ResourceId("unit-a:i2")],
        agent=agent_container,
        token=SessionToken("token"),
    )

    instrument_info = InstrumentInfo(
        id=ResourceId("invalid_id"),
        port_id=ResourceId("unit-a:p1"),
        definition=InstrumentDefinition(
            alias="alias",
            mode=InstrumentMode.UNSPECIFIED,
            role=InstrumentRole.TRANSCEIVER,
            profile=FixedTimelineProfile(
                frequency_range_min=5_000_000_000, frequency_range_max=5_100_000_000
            ),
        ),
        config=FixedTimelineConfig(sampling_period_fs=400_000, bitdepth=16),
    )

    with pytest.raises(ValueError):
        create_instrument_driver_fixed_timeline(session, instrument_info)
