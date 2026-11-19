import logging

import numpy as np
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
from quelware_core.entities.waveform.sampled import IqWaveform

from quelware_client.core import Session
from quelware_client.core._agent_container import AgentContainer
from quelware_client.core.instrument_driver import (
    InstrumentDriver,
    create_instrument_driver_fixed_timeline,
)
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock


def _create_inst_driver():
    inst_agent = InstrumentAgentMock()
    agent_container = AgentContainer()
    agent_container.update_instrument_agent(UnitLabel("unit-a"), inst_agent)
    session = Session(
        resource_ids=[ResourceId("unit-a:i1")],
        agent=agent_container,
        token=SessionToken("token"),
    )
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
        FixedTimelineConfig(
            sampling_period_fs=400_000,
            bitdepth=16,
            timeline_step_samples=256,
            samples_per_tick=4,
        ),
        inst_agent,
        session,
    )
    return inst_driver


@pytest.mark.asyncio
async def test_apply():
    inst_driver = _create_inst_driver()

    ds = [directives.SetFrequency(60_000_000), directives.SetPhaseOffset(120)]
    for d in ds:
        await inst_driver.apply(d)


_LOGGER = "quelware_client.core.instrument_driver"


@pytest.mark.asyncio
@pytest.mark.parametrize("with_frequency", [False, True])
async def test_an_applied_timeline_is_logged_with_its_size_and_the_instrument(
    caplog, with_frequency
):
    inst_driver = _create_inst_driver()
    timeline = directives.SetFixedTimeline(
        waveform_library=[
            IqWaveform(sampling_period_fs=400_000, iq_array=np.ones(8, complex)),
            IqWaveform(sampling_period_fs=400_000, iq_array=np.ones(4, complex)),
        ],
        events=[
            directives.WaveformEvent(
                waveform_index=i % 2,
                start_offset_samples=16 * i,
                gain=1.0,
                phase_offset_deg=0.0,
            )
            for i in range(3)
        ],
        capture_windows=[],
        length=256,
        iterations=1,
    )

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        if with_frequency:
            await inst_driver.apply([directives.SetFrequency(5_050_000_000), timeline])
        else:
            await inst_driver.apply(timeline)

    (record,) = caplog.records
    assert record.levelno == logging.INFO
    assert record.getMessage().startswith(
        "applied a timeline of 3 events and 12 waveform samples "
        "to unit-a:p1 (alias) in "
    )


@pytest.mark.asyncio
async def test_applying_no_timeline_is_not_logged(caplog):
    inst_driver = _create_inst_driver()

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await inst_driver.apply(directives.SetFrequency(5_050_000_000))

    assert caplog.records == []


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
        config=FixedTimelineConfig(
            sampling_period_fs=400_000,
            bitdepth=16,
            timeline_step_samples=64,
            samples_per_tick=4,
        ),
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
        config=FixedTimelineConfig(
            sampling_period_fs=400_000,
            bitdepth=16,
            timeline_step_samples=256,
            samples_per_tick=4,
        ),
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
        config=FixedTimelineConfig(
            sampling_period_fs=400_000,
            bitdepth=16,
            timeline_step_samples=256,
            samples_per_tick=4,
        ),
    )

    with pytest.raises(ValueError):
        create_instrument_driver_fixed_timeline(session, instrument_info)
