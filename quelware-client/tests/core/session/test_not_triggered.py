from collections.abc import Collection

import pytest
from quelware_core.entities.instrument import (
    FixedTimelineConfig,
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.session import SessionToken
from quelware_core.entities.unit import UnitLabel

from quelware_client.core import AgentContainer, Session
from quelware_client.core.exceptions import (
    NotTriggeredError,
    ServiceUnavailableError,
)
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)
from quelware_client.testing.instrument_agent_mock import InstrumentAgentMock
from quelware_client.testing.trigger_agent_mock import TriggerAgentMock
from quelware_client.testing.worker_agent_mock import WorkerAgentMock

_A1 = ResourceId("unit-a:i1")
_A2 = ResourceId("unit-a:i2")
_B1 = ResourceId("unit-b:i1")


class _Agent(InstrumentAgentMock):
    """Counts the fetches that reach the unit, and fails an arm or a self-timed
    trigger when told to."""

    def __init__(self) -> None:
        self.fetched: list[ResourceId] = []
        self.fail_arm = False
        self.fail_trigger_now = False
        # the triggers the client made by itself: "now" or the count scheduled
        self.self_triggers: list[str | int] = []

    async def arm(
        self, token: SessionToken, resource_ids: Collection[ResourceId]
    ) -> bool:
        if self.fail_arm:
            raise RuntimeError("arm refused")
        return True

    async def trigger_now(
        self, token: SessionToken, min_wait_ms: int | None = None
    ) -> int:
        if self.fail_trigger_now:
            raise RuntimeError("trigger lost")
        self.self_triggers.append("now")
        return 1234

    async def schedule_trigger(self, token: SessionToken, target_time: int) -> bool:
        self.self_triggers.append(target_time)
        return True

    async def fetch_result(
        self, token: SessionToken, resource_id: ResourceId
    ) -> ResultContainer:
        self.fetched.append(resource_id)
        return ResultContainer()

    async def wait_for_result(
        self,
        token: SessionToken,
        resource_id: ResourceId,
        timeout_sec: float | None,
    ) -> ResultContainer:
        self.fetched.append(resource_id)
        return ResultContainer()


class _FailingTriggerAgent(TriggerAgentMock):
    async def trigger(self, token, instrument_ids, requested_min_wait_ms) -> int:
        raise RuntimeError("trigger lost")


class _NoManagerTriggerAgent(TriggerAgentMock):
    """A manager without a trigger service, so the client triggers by itself."""

    async def trigger(self, token, instrument_ids, requested_min_wait_ms) -> int:
        raise ServiceUnavailableError()


def _session(agent: _Agent, trigger_agent: TriggerAgentMock | None = None) -> Session:
    agents = AgentContainer()
    agents.trigger = trigger_agent or TriggerAgentMock()
    for unit in ("unit-a", "unit-b"):
        agents.update_instrument_agent(UnitLabel(unit), agent)
        agents.update_worker_agent(UnitLabel(unit), WorkerAgentMock())
    return Session([_A1, _A2, _B1], agents, token=SessionToken("tok"))


def _info(rid: ResourceId) -> InstrumentInfo:
    return InstrumentInfo(
        id=rid,
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


@pytest.mark.asyncio
async def test_an_instrument_never_triggered_is_not_waited_for() -> None:
    agent = _Agent()

    with pytest.raises(NotTriggeredError, match="unit-a:i1"):
        await _session(agent).wait_for_results([_A1])

    assert agent.fetched == []


@pytest.mark.asyncio
async def test_an_instrument_of_a_trigger_that_failed_is_not_waited_for() -> None:
    agent = _Agent()
    session = _session(agent)
    await session.trigger([_A1])
    session._agent.trigger = _FailingTriggerAgent()

    with pytest.raises(RuntimeError, match="trigger lost"):
        await session.trigger([_A1])

    with pytest.raises(NotTriggeredError):
        await session.wait_for_results([_A1])
    assert agent.fetched == []


@pytest.mark.asyncio
async def test_a_later_trigger_on_the_unit_replaces_the_run_there() -> None:
    agent = _Agent()
    session = _session(agent)
    await session.trigger([_A1])
    await session.trigger([_A2])

    with pytest.raises(NotTriggeredError, match="unit-a:i1"):
        await session.wait_for_results([_A1])

    assert set(await session.wait_for_results([_A2])) == {_A2}


@pytest.mark.asyncio
async def test_a_trigger_on_one_unit_keeps_the_run_on_another() -> None:
    session = _session(_Agent())
    await session.trigger([_A1, _B1])
    await session.trigger([_A2])

    assert set(await session.wait_for_results([_A2, _B1])) == {_A2, _B1}


@pytest.mark.asyncio
async def test_a_driver_waits_only_for_a_triggered_instrument() -> None:
    agent = _Agent()
    session = _session(agent)
    driver = create_instrument_driver_fixed_timeline(session, _info(_A1))

    with pytest.raises(NotTriggeredError):
        await driver.wait_for_result()
    with pytest.raises(NotTriggeredError):
        await driver.fetch_result()
    assert agent.fetched == []

    await session.trigger([_A1])

    await driver.wait_for_result()
    await driver.fetch_result()
    assert agent.fetched == [_A1, _A1]


@pytest.mark.asyncio
async def test_initializing_an_instrument_drops_the_run_on_its_unit() -> None:
    session = _session(_Agent())
    driver = create_instrument_driver_fixed_timeline(session, _info(_A1))
    await session.trigger([_A1, _A2, _B1])

    await driver.initialize()

    with pytest.raises(NotTriggeredError, match=r"unit-a:i1.*unit-a:i2"):
        await session.wait_for_results([_A1, _A2])
    assert set(await session.wait_for_results([_B1])) == {_B1}


@pytest.mark.asyncio
async def test_a_wait_with_one_untriggered_instrument_asks_for_none() -> None:
    agent = _Agent()
    session = _session(agent)
    await session.trigger([_A1])

    with pytest.raises(NotTriggeredError) as raised:
        await session.wait_for_results([_A1, _B1])

    assert raised.value.rids == [_B1]
    assert agent.fetched == []


@pytest.mark.asyncio
async def test_the_session_s_own_fetch_and_wait_ask_only_after_a_trigger() -> None:
    agent = _Agent()
    session = _session(agent)

    with pytest.raises(NotTriggeredError):
        await session.fetch_result(_A1)
    with pytest.raises(NotTriggeredError):
        await session.wait_for_result(_A1)
    assert agent.fetched == []

    await session.trigger([_A1])

    await session.fetch_result(_A1)
    await session.wait_for_result(_A1)
    assert agent.fetched == [_A1, _A1]


@pytest.mark.asyncio
async def test_a_run_can_be_waited_for_again() -> None:
    agent = _Agent()
    session = _session(agent)
    await session.trigger([_A1])

    await session.wait_for_results([_A1])
    await session.wait_for_results([_A1])

    assert agent.fetched == [_A1, _A1]


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [[_A1], [_A1, _B1]], ids=["one unit", "two units"])
async def test_a_trigger_made_by_the_client_itself_is_waited_for(ids) -> None:
    agent = _Agent()
    session = _session(agent, _NoManagerTriggerAgent())

    await session.trigger(ids)

    # one unit triggers itself; several are scheduled at one count each
    if len(ids) == 1:
        assert agent.self_triggers == ["now"]
    else:
        assert len(agent.self_triggers) == 2
        assert len(set(agent.self_triggers)) == 1
    assert set(await session.wait_for_results(ids)) == set(ids)


@pytest.mark.asyncio
async def test_a_self_timed_trigger_that_failed_is_not_waited_for() -> None:
    agent = _Agent()
    agent.fail_trigger_now = True
    session = _session(agent, _NoManagerTriggerAgent())

    with pytest.raises(RuntimeError, match="trigger lost"):
        await session.trigger([_A1])

    with pytest.raises(NotTriggeredError):
        await session.wait_for_results([_A1])


@pytest.mark.asyncio
async def test_an_arm_that_failed_drops_the_run_on_its_unit() -> None:
    agent = _Agent()
    session = _session(agent)
    await session.trigger([_A1, _B1])
    agent.fail_arm = True

    with pytest.raises(RuntimeError, match="arm refused"):
        await session.trigger([_A2])

    with pytest.raises(NotTriggeredError):
        await session.wait_for_results([_A1])
    assert set(await session.wait_for_results([_B1])) == {_B1}
