# Instruments

An **instrument** is an abstraction of a control device that you deploy onto a
**port** of a unit to transmit and/or capture microwave signals. It lets you
describe *what* you want to do, while the system takes care of *how* the
hardware does it.

An instrument hides implementation details such as AWG bandwidth, digital
filters, and up-conversion. The system also applies the appropriate phase
conversions automatically — so the phase consistency that is essential for
quantum experiments is guaranteed at the system level — and it handles signal
multiplexing on your behalf.

!!! note

    The parameters you set on an instrument describe the **result you want**.
    They do not necessarily correspond one-to-one to the underlying
    implementation parameters.

## Anatomy

An instrument is described by an `InstrumentDefinition` with four parts:

- **Alias** — a human-friendly name you choose (e.g. `"readout"`). Within a
  session the alias is scoped to its unit.
- **Role** — what the instrument does:
    - `TRANSMITTER` — output signals only.
    - `RECEIVER` — capture signals only.
    - `TRANSCEIVER` — output and capture.
    - `TRANSCEIVER_LOOPBACK` — output and capture routed internally, useful for
      trying things out without an external device.
- **Mode** — how the instrument is programmed; see [Mode](#mode) below.
- **Profile** — mode-specific settings. For a fixed-timeline instrument this is
  a `FixedTimelineProfile` giving the frequency range it will operate in.

## Mode

An instrument's **mode** determines the kind of directives it accepts and how
it runs. You choose the mode when you deploy the instrument. `FIXED_TIMELINE`
is currently the only mode; others may be added in the future.

### `FIXED_TIMELINE`

The instrument plays a pre-scheduled timeline of waveform events and capture
windows on precise hardware timing. This is the mode used throughout the
[Tutorial](../tutorials/fixed-timeline.md).

## Deploying

You deploy an instrument onto a port within a session with
[`Session.deploy_instruments()`](../client/api/session.md). Deployment returns
an `InstrumentInfo`, which carries:

- the instrument's **id** — a resource id you use to drive and trigger it, and
- its **config** — hardware timing such as the sampling period and timeline
  step, which the [`Sequencer`](../client/api/helpers.md) needs to place events
  on the sample grid.

## Running

How an instrument runs depends on its mode. A `FIXED_TIMELINE` instrument is
run in three moves:

1. Build a timeline of waveform events and capture windows with a `Sequencer`.
2. Apply configuration — frequency, capture mode, and the timeline — to the
   instrument.
3. Trigger it, then fetch the captured result.

See the [Tutorial](../tutorials/fixed-timeline.md) for a worked example.
