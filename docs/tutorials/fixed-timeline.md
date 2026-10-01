# Fixed-timeline tutorial

This tutorial builds a simple measurement on `FIXED_TIMELINE` instruments: a
*drive* instrument sends a pulse, and a *readout* instrument then sends its own
pulse and captures the response. It takes four steps: deploy the instruments,
program their pulses with the sequencer, trigger them, and wait for their
results. It assumes you have finished [Getting started](../getting-started.md).

The code is the script
[`examples/fixed_timeline.py`](https://github.com/quel-inc/quelware-client/blob/main/quelware-client/examples/fixed_timeline.py),
which you can run as it is:

```sh
python fixed_timeline.py <host> --unit <label>
```

It deploys a drive on the transmitter port `tx_p02` and a readout on the
transceiver port `trx_p00p01`; choose other ports with `--drive-port` and
`--readout-port`.

Deploying an instrument is easier once you know what one is — see
[Instruments](../concepts/instruments.md) for the concept.

The imports used throughout:

```python
--8<-- "quelware-client/examples/fixed_timeline.py:imports"
```

## Step 1: Deploy the instruments

An [instrument](../concepts/instruments.md) is a logical device you place on a
port. Open a session over the two ports, such as `quel3-01-028:tx_p02` and
`quel3-01-028:trx_p00p01`, and deploy a transmitter for the drive and a
transceiver for the readout:

```python
--8<-- "quelware-client/examples/fixed_timeline.py:deploy"
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
--8<-- "quelware-client/examples/fixed_timeline.py:timeline"
```

Both instruments start their timelines at the same trigger, so the offsets line
up: the drive pulse plays at 0 ns, and the readout pulse after it.

## Step 3: Trigger the instruments

Create a driver for each instrument and apply its frequency and timeline, and
for the readout the capture mode. Then trigger both instruments at once:

```python
--8<-- "quelware-client/examples/fixed_timeline.py:trigger"
```

`driver.apply()` only sends the settings; the unit puts them on the device when
you trigger. `trigger()` starts every instrument you pass at the same time, a
little after now.

## Step 4: Wait for the results

Wait for every instrument you triggered, also the drive, which captures
nothing:

```python
--8<-- "quelware-client/examples/fixed_timeline.py:wait"
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
--8<-- "quelware-client/examples/fixed_timeline.py:main"
```

## Next steps

- [Instruments](../concepts/instruments.md) — the concept behind Step 1
- [Triggering](../concepts/triggering.md) — how a run starts, and how it fails
- [API Reference](../client/api/index.md) — `Session`, `Sequencer`, and more
