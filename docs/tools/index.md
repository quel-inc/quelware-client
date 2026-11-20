# Tools

`quelware-tools` is a set of command-line tools and diagnostics for QuEL
systems, built on [`quelware-client`](../client/index.md). Use them to check a
system after you set it up or update it, to measure its timing, and to put load
on it. They run against an already-running system — you give them an endpoint
and a PAT; they start nothing themselves.

## Install

```sh
pip install quelware-tools          # tools only
pip install "quelware-tools[plot]"  # + matplotlib, for the commands that plot
```

## Authentication

The commands use a PAT (see [Access control](../concepts/access-control.md)).
They default to the PAT configured for `quelware-client`; every command but
`quel-echo-test` lets you override it with `--pat`. `quel-soak-compare` only
reads files. It does not connect to a system and does not need a PAT.

## At a glance

| Command | What it is for | PAT | Needs | Runs on |
| ------- | -------------- | --- | ----- | ------- |
| [`quel-echo-test`](#quel-echo-test) | A first run after you install | privileged | a free trx port | one port |
| [`quel-tone-test`](#quel-tone-test) | Health check after an update | admin | an idle unit | every tx/trx port of a unit |
| [`quel-pulse-test`](#quel-pulse-test) | Health check of pulse timing and length | admin | an idle unit | every tx/trx port of a unit |
| [`quel-measure-delay`](#quel-measure-delay) | Path delay of each port | admin | an idle unit | every tx/trx port of a unit |
| [`quel-trigger-wait-test`](#quel-trigger-wait-test) | How short a trigger wait the units start in time on | privileged | free tx/trx ports | one or more units |
| [`quel-soak-test`](#quel-soak-test) | Put load on the units and time each step | privileged | free tx/trx ports | one or more units |
| [`quel-soak-compare`](#quel-soak-compare) | Compare the timings of two soak tests | none | two `--timings` files | your machine |
| [`quel-unit-config`](#quel-unit-config) | Show or set a unit's controls | any (`show`), admin (`set`) | an idle unit (`set`) | one unit |
| [`quel-recover-past-counter`](#quel-recover-past-counter) | Back to normal after `past_counter`, without a reboot | privileged | nobody else on the units | every port of the units |

"Privileged" means a `PRIVILEGED_USER` or `ADMIN` PAT: these commands deploy
instruments. An idle unit has no deployed instruments; `--discard-instruments`
clears them first. The commands that
use the monitor put it into loopback and set it back to `open` when they end.

Every test exits non-zero when something fails, so you can run it from a script.

## First run

### `quel-echo-test`

Emits a pulse on a transceiver port and captures the echoed response. With
`--loopback` the signal is routed inside the unit, so you need no external
device. `--iq-plot` shows the I/Q trace (needs the `plot` extra).

```sh
quel-echo-test <host> --loopback
quel-echo-test <host> --port-id <unit>:<trx-port> --iq-plot
```

## Health checks

Run these after an on-site software update.

### `quel-tone-test`

Emits a tone on every tx/trx port of a unit, one port at a time, and checks
that it shows up on the monitor.

```sh
quel-tone-test <host> --unit <label>
```

### `quel-pulse-test`

Emits a train of pulses of several lengths and gaps on every tx/trx port, and
checks on the monitor that each pulse starts where it was put, is as long as it
was, and that no other pulse shows up. The lengths and gaps include the ones
where the server joins pulses into one send or splits them. `--plot-iq DIR`
saves each port's capture there as a PNG plot and a raw `.npy` (needs the
`plot` extra).

```sh
quel-pulse-test <host> --unit <label>
quel-pulse-test <host> --unit <label> --length-ticks 4 --length-ticks 16 --gap-ticks 0 --gap-ticks 8
```

## Timing

### `quel-measure-delay`

Measures the delay from each tx/trx port to the monitor: one port at a time, it
emits a pulse and times its arrival. With `--verify`, it then delays every port
by its measured amount, emits a comb of pulses on all of them at once, and
checks that each pulse lands where intended. `--verify-plot-iq DIR` saves the
comb capture as a PNG plot and a raw `.npy` (needs the `plot` extra).

```sh
quel-measure-delay <host> --unit <label>
quel-measure-delay <host> --unit <label> --verify
```

### `quel-trigger-wait-test`

Finds how short a trigger wait works on your system (see
[Triggering](../concepts/triggering.md)). It sends a short pulse on every
tx/trx port of the units, triggers them all at once many times at each of a
set of waits (150 to 600 ms by default), and reports for each wait how many
runs completed and why the others failed. Without `--unit` it runs on every
unit.

```sh
quel-trigger-wait-test <host>
quel-trigger-wait-test <host> --unit <label> --wait-ms 150 --wait-ms 200 --runs-per-wait 50
```

## Load

### `quel-soak-test`

Puts load on the units and measures how long each step takes. The load
imitates typical tasks for the characterization and calibration of qubits. A
run is one trigger on every tx/trx port of the units at the same time.

By default, the test does one round of 68 runs and then stops. A round has
these kinds of runs:

- `sparse`, `spectroscopy` and `dense-cr`: light loads, 20 runs each.
- `packed-sweep`: 50 points of a calibration sweep in one trigger, 4 runs.
- `packed-rb-1024` and `packed-rb-2048`: 30 randomized benchmarking sequences
  of 1024 or 2048 gates in one trigger, 2 runs each.

The order of the kinds in a round is always the same. The seed decides the
waves and the capture windows of each run. The test counts failed runs by
kind.

Options:

- `--kind NAME`: use only this kind. Repeat the option to use more kinds.
- `--rounds N`, `--runs N` and `--duration-sec S`: limit the length of the
  test. The test stops at the first limit that it reaches. With only
  `--duration-sec`, it continues for that time. With `--runs 0`, it continues
  until you stop it.
- `--save-dir DIR`: save the plan of each failed run as JSON. To repeat a
  failed run, give its seed and run index, and the same `--kind` options.
- `--initialize-each-run`: initialize the instruments at the start of each
  run, like a client that starts each run from a clean state.

```sh
quel-soak-test <host> --unit <label>
quel-soak-test <host> --unit <label> --kind sparse --kind spectroscopy --runs 200
quel-soak-test <host> --unit <label> --runs 1000 --save-dir ./failed
quel-soak-test <host> --unit <label> --seed 7 --start-run 42 --runs 1   # repeat a run
```

### `quel-soak-compare`

Compares the timings of two soak tests, for example before and after a server
update.

1. Run `quel-soak-test` with `--timings FILE`. The test writes the units, the
   settings and the time of each step of each run to `FILE` as JSON.
2. Give two such files to `quel-soak-compare`.

For each step and each kind, it shows the median, the 95th percentile and the
maximum time of the completed runs. If the two tests used the same seed, the
same kinds and the same ports, they did the same runs. In that case, it also
shows the median difference between the runs with the same index.

```sh
quel-soak-test <host> --unit <label> --timings before.json
quel-soak-test <host> --unit <label> --timings after.json
quel-soak-compare before.json after.json --label-a before --label-b after
```

## Configuration

### `quel-unit-config`

Shows or sets a unit's configuration controls. Find the keys with `show`.

```sh
quel-unit-config show <host> --unit <label>
quel-unit-config set <host> --unit <label> KEY=VALUE
```

## Recovery

### `quel-recover-past-counter`

A temporary workaround that brings a unit back to normal after a run failed
with `past_counter`, without a reboot. It removes the instruments on every port
of the units, so run it only when nobody else uses them.

```sh
quel-recover-past-counter <host> --unit <label>
```

## From Python

The tests are also functions in `quelware_tools.diagnostics`: `run_tone_test`,
`run_pulse_test`, `run_delay_test`, `run_trigger_wait_test` and `run_soak_test`.
Each takes a client and returns a report.

```python
from quelware_client import create_quelware_client
from quelware_tools.diagnostics import run_tone_test

async def check(host: str, unit: str) -> bool:
    qc = create_quelware_client(host, 50051)
    async with qc:
        report = await run_tone_test(qc, unit)
    return report.passed
```
