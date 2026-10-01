# Fixed-timeline tutorial

This tutorial builds a simple measurement on `FIXED_TIMELINE` instruments: a
*drive* instrument sends a pulse, and a *readout* instrument then sends its own
pulse and captures the response. It takes four steps: deploy the instruments,
program their pulses with the sequencer, trigger them, and wait for their
results. It assumes you have finished [Getting started](../getting-started.md).

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
from quelware_client.core.exceptions import RunFailedError
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)

UNIT = "quel3-01-028"              # your unit label
READOUT_PORT = f"{UNIT}:trx_p00p01"  # a transceiver port on that unit
DRIVE_PORT = f"{UNIT}:tx_p02"        # a transmitter port on that unit
```

## Step 1: Deploy the instruments

An [instrument](../concepts/instruments.md) is a logical device you place on a
port. Open a session over the ports and deploy a transmitter for the drive and
a transceiver for the readout:

```python
def definition(alias, role, center_hz):
    return InstrumentDefinition(
        alias=alias,
        mode=InstrumentMode.FIXED_TIMELINE,
        role=role,
        profile=FixedTimelineProfile(
            frequency_range_min=center_hz - 2.5e6,
            frequency_range_max=center_hz + 2.5e6,
        ),
    )


async def deploy(qc):
    async with qc.create_session([DRIVE_PORT, READOUT_PORT]) as session:
        (drive,) = await session.deploy_instruments(
            DRIVE_PORT, [definition("drive", InstrumentRole.TRANSMITTER, 5.0e9)]
        )
        (readout,) = await session.deploy_instruments(
            READOUT_PORT,
            [definition("readout", InstrumentRole.TRANSCEIVER_LOOPBACK, 6.0e9)],
        )
    return drive, readout
```

`deploy_instruments()` returns an `InstrumentInfo` for each deployed instrument
— its id and its hardware timing (`config`), both of which the next steps need.
The readout uses `TRANSCEIVER_LOOPBACK`, which routes its output back to its
input inside the unit, so you can try this without an external device.

## Step 2: Program the pulses with the sequencer

The [`Sequencer`](../client/api/helpers.md) builds a *fixed timeline*: a schedule
of waveform events and capture windows, expressed in nanoseconds from the
trigger. Bind it to an instrument's timing, register a waveform, then place an
event, and a capture window for the readout:

```python
def build_timeline(inst_info, pulse_start_ns, capture):
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
    seq.add_event(alias, "pulse", start_offset_ns=pulse_start_ns)
    if capture:
        seq.add_capture_window(
            alias, "capture", start_offset_ns=pulse_start_ns, length_ns=1000.0
        )
    seq.extend_length_ns(100_000.0)  # gap before the next shot
    seq.set_iterations(1000)         # average over 1000 shots
    return seq
```

Both instruments start their timelines at the same trigger, so the offsets line
up: the drive pulse plays at 0 ns, and the readout pulse after it.

## Step 3: Trigger the instruments

Create a driver for each instrument and apply its frequency and timeline, and
for the readout the capture mode. Then trigger both instruments at once:

```python
async def configure(session, inst_info, hz, seq, capture):
    driver = create_instrument_driver_fixed_timeline(session, inst_info)
    alias = inst_info.definition.alias
    settings = [directives.SetFrequency(hz=hz)]
    if capture:
        settings.append(
            directives.SetCaptureMode(mode=directives.CaptureMode.AVERAGED_WAVEFORM)
        )
    settings.append(seq.export_set_fixed_timeline_directive(alias))
    await driver.initialize()
    await driver.apply(settings)


async def trigger(session, drive, readout):
    await configure(
        session, drive, 5.0e9, build_timeline(drive, 0.0, capture=False), False
    )
    await configure(
        session, readout, 6.0e9, build_timeline(readout, 300.0, capture=True), True
    )
    await session.trigger([drive.id, readout.id])
```

`driver.apply()` only sends the settings; the unit puts them on the device when
you trigger. `trigger()` starts every instrument you pass at the same time, a
little after now.

## Step 4: Wait for the results

Wait for every instrument you triggered, also the drive, which captures
nothing:

```python
async def wait(session, drive, readout):
    try:
        results = await session.wait_for_results(
            [drive.id, readout.id], timeout_sec=10.0
        )
    except RunFailedError as e:
        for instrument_id, error in e.failures.items():
            print(f"{instrument_id} failed: {error}")
        raise
    return results[readout.id].iq_waveform_result["capture"][0].iq_array
```

`wait_for_results()` returns when every instrument you pass has finished, with
the result of each; the drive's result is empty. Waiting for the drive as well
tells you whether its pulse played: if the unit could not play it, you get its
error instead of a capture that silently lacks the drive.

If any instrument fails, `wait_for_results()` still waits for all of them, and
then raises `RunFailedError`. Its `failures` holds the error of each instrument
that failed, as the unit reported it, and its `results` holds the results of
the others. Pass a `timeout_sec` a little longer than your run takes, so that a
run that never ends does not hold you forever.

See [Triggering](../concepts/triggering.md) for how a run starts, and the ways
it can fail.

## Putting it together

```python
async def main():
    qc = create_quelware_client("192.0.2.1", 50051)  # your server address
    async with qc:
        drive, readout = await deploy(qc)
        async with qc.create_session([drive.id, readout.id], ttl_ms=10_000) as session:
            await trigger(session, drive, readout)
            iq = await wait(session, drive, readout)
    print(f"captured {len(iq)} samples")


asyncio.run(main())
```

## Next steps

- [Instruments](../concepts/instruments.md) — the concept behind Step 1
- [Triggering](../concepts/triggering.md) — how a run starts, and how it fails
- [API Reference](../client/api/index.md) — `Session`, `Sequencer`, and more
