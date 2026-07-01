# Fixed-timeline tutorial

This tutorial builds a simple readout measurement on a `FIXED_TIMELINE`
instrument, in three steps: deploy an instrument, program a pulse with the
sequencer, and execute it. It assumes you have finished
[Getting started](../getting-started.md).

Deploying an instrument is easier once you know what one is — see
[Instruments](../concepts/instruments.md) for the concept.

The imports and constants used throughout:

```python
import asyncio

import numpy as np
from quelware_core.entities import directives
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentMode,
    InstrumentRole,
)

from quelware_client import create_quelware_client
from quelware_client.client.helpers.sequencer import Sequencer
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)

UNIT = "quel3-01-028"        # your unit label
PORT = f"{UNIT}:trx_p00p01"  # a transceiver port on that unit
```

## Step 1: Deploy an instrument

An [instrument](../concepts/instruments.md) is a logical device you place on a
port. Open a session over the port and deploy a transceiver into it:

```python
async def deploy(qc):
    async with qc.create_session([PORT]) as session:
        definition = InstrumentDefinition(
            alias="readout",
            mode=InstrumentMode.FIXED_TIMELINE,
            role=InstrumentRole.TRANSCEIVER_LOOPBACK,
            profile=FixedTimelineProfile(
                frequency_range_min=5.9975e9,
                frequency_range_max=6.0025e9,
            ),
        )
        inst_infos = await session.deploy_instruments(PORT, definitions=[definition])
    return inst_infos[0]
```

`deploy_instruments()` returns an `InstrumentInfo` describing the deployed
instrument — its id and its hardware timing (`config`), both of which the next
steps need.

## Step 2: Program a pulse with the sequencer

The [`Sequencer`](../client/api/helpers.md) builds a *fixed timeline*: a schedule
of waveform events and capture windows, expressed in nanoseconds. Bind it to the
instrument's timing, register a waveform, then place an event and a capture
window:

```python
def build_timeline(inst_info):
    alias = inst_info.definition.alias
    sampling_period_ns = inst_info.config.sampling_period_fs * 1e-6

    seq = Sequencer(default_sampling_period_ns=sampling_period_ns)
    seq.bind(
        alias,
        sampling_period_fs=inst_info.config.sampling_period_fs,
        step_samples=inst_info.config.timeline_step_samples,
    )

    n = int(200.0 / sampling_period_ns)  # a 200 ns rectangular pulse
    seq.register_waveform("pulse", np.ones(n, dtype=complex))
    seq.add_event(alias, "pulse", start_offset_ns=0.0)
    seq.add_capture_window(alias, "capture", start_offset_ns=0.0, length_ns=1000.0)
    seq.extend_length_ns(100_000.0)  # gap before the next shot
    seq.set_iterations(1000)         # average over 1000 shots
    return seq
```

## Step 3: Execute the instrument

Create an instrument driver, apply the frequency, capture mode, and timeline,
then trigger and fetch the result:

```python
async def run(qc, inst_info):
    async with qc.create_session([inst_info.id], ttl_ms=10_000) as session:
        driver = create_instrument_driver_fixed_timeline(session, inst_info)
        seq = build_timeline(inst_info)

        await driver.initialize()
        await driver.apply(
            [
                directives.SetFrequency(hz=6.0e9),
                directives.SetCaptureMode(mode=directives.CaptureMode.AVERAGED_WAVEFORM),
                seq.export_set_fixed_timeline_directive(inst_info.definition.alias),
            ]
        )
        await session.trigger([inst_info.id])
        result = await driver.fetch_result()

    return result.iq_waveform_result["capture"][0].iq_array
```

## Putting it together

```python
async def main():
    qc = create_quelware_client("192.0.2.1", 50051)  # your server address
    async with qc:
        inst_info = await deploy(qc)
        iq = await run(qc, inst_info)
    print(f"captured {len(iq)} samples")


asyncio.run(main())
```

## Next steps

- [Instruments](../concepts/instruments.md) — the concept behind Step 1
- [API Reference](../client/api/index.md) — `Session`, `Sequencer`, and more
