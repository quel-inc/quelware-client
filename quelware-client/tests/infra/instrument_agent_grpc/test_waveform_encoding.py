import numpy as np
import pytest
import quelware_core.pb.quelware.instrument.v1 as pb_inst
import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.directives import SetFixedTimeline
from quelware_core.entities.resource import ResourceId
from quelware_core.entities.session import SessionToken
from quelware_core.entities.waveform.sampled import IqWaveform
from quelware_core.features import known

from quelware_client.core.interfaces.worker_agent import UnitVersion
from quelware_client.infra.instrument_agent_grpc import (
    InstrumentAgentGrpc,
    reads_dense_waveforms,
)

TOKEN = SessionToken("t")
RID = ResourceId("unit-a:r1")
TIMELINE = SetFixedTimeline(
    waveform_library=[
        IqWaveform(sampling_period_fs=400_000, iq_array=np.array([0.5 + 0.25j]))
    ],
    events=[],
    capture_windows=[],
    length=256,
    iterations=1,
)


class _Instrument:
    metadata = None

    def __init__(self) -> None:
        self.requests: list[pb_inst.ConfigureRequest] = []

    async def configure(self, req, metadata=None, timeout=None):
        self.requests.append(pb_inst.ConfigureRequest.parse(bytes(req)))
        return pb_inst.ConfigureResponse()


async def _sent_waveform(use_dense_waveforms: bool) -> pb_models.Waveform:
    agent = InstrumentAgentGrpc.__new__(InstrumentAgentGrpc)
    instrument = _Instrument()
    agent._service = instrument
    agent._use_dense_waveforms = use_dense_waveforms

    await agent.configure(TOKEN, RID, [TIMELINE])

    (req,) = instrument.requests
    (directive,) = req.directives
    assert directive.fixed_timeline_sampled_waveform is not None
    timeline = directive.fixed_timeline_sampled_waveform.set_timeline
    assert timeline is not None
    (waveform,) = timeline.waveform_library
    return waveform


@pytest.mark.asyncio
async def test_waveforms_go_as_bytes_from_an_agent_made_to_use_them() -> None:
    waveform = await _sent_waveform(use_dense_waveforms=True)

    assert waveform.sampled is None
    assert waveform.dense is not None


@pytest.mark.asyncio
async def test_waveforms_go_as_samples_otherwise() -> None:
    waveform = await _sent_waveform(use_dense_waveforms=False)

    assert waveform.dense is None
    assert waveform.sampled is not None


def test_only_a_unit_that_names_dense_waveform_reads_waveforms_as_bytes():
    assert reads_dense_waveforms(UnitVersion("1.0", known(["dense_waveform"])))
    assert not reads_dense_waveforms(UnitVersion("0.5.0"))
    assert not reads_dense_waveforms(None)
