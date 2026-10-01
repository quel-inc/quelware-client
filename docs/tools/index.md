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
`quel-echo-test` lets you override it with `--pat`.

## At a glance

| Command | What it is for | PAT | Needs | Runs on |
| ------- | -------------- | --- | ----- | ------- |
| [`quel-echo-test`](#quel-echo-test) | A first run after you install | privileged | a free trx port | one port |
| [`quel-tone-test`](#quel-tone-test) | Health check after an update | admin | an idle unit | every tx/trx port of a unit |
| [`quel-pulse-test`](#quel-pulse-test) | Health check of pulse timing and length | admin | an idle unit | every tx/trx port of a unit |
| [`quel-measure-delay`](#quel-measure-delay) | Path delay of each port | admin | an idle unit | every tx/trx port of a unit |
| [`quel-trigger-wait-test`](#quel-trigger-wait-test) | How short a trigger wait the units start in time on | privileged | free tx/trx ports | one or more units |
| [`quel-soak-test`](#quel-soak-test) | Load over a long time | privileged | free tx/trx ports | one or more units |
| [`quel-unit-config`](#quel-unit-config) | Show or set a unit's controls | any (`show`), admin (`set`) | an idle unit (`set`) | one unit |

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

Keeps the units busy with random trains of waves on every tx/trx port, and
random capture windows on every trx port, all under one trigger per run. It
runs until a number of runs or a duration is spent, and logs how long each
step of a run took. A failed run is counted by its kind; `--save-dir` saves
its plan as JSON, which you can replay from its seed and run index.
`--initialize-each-run` initializes the instruments at the start of every run,
as a client that starts each run afresh does.

```sh
quel-soak-test <host> --duration-sec 3600
quel-soak-test <host> --unit <label> --runs 1000 --save-dir ./failed
quel-soak-test <host> --unit <label> --seed 7 --start-run 42 --runs 1   # replay a run
```

## Configuration

### `quel-unit-config`

Shows or sets a unit's configuration controls. Find the keys with `show`.

```sh
quel-unit-config show <host> --unit <label>
quel-unit-config set <host> --unit <label> KEY=VALUE
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
