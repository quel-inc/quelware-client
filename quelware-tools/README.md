# quelware-tools

[![PyPI](https://img.shields.io/pypi/v/quelware-tools)](https://pypi.org/project/quelware-tools/)
[![License](https://img.shields.io/pypi/l/quelware-tools)](https://github.com/quel-inc/quelware-client/blob/main/quelware-tools/LICENSE)

Command-line tools and diagnostics for QuEL systems, built on `quelware-client`.

They run against an already-running manager + edge server (endpoint + PAT); they
start nothing themselves.

## Commands

- `quel-echo-test` — emit a pulse on a TRX port and capture the echoed response
  (optionally plotting the I/Q trace; install with the `plot` extra). A first
  run after you install.
- `quel-tone-test` — put the unit's monitor into loopback, emit a tone on every
  tx/trx port, and check it appears in the monitor capture. A health check
  after an update. Needs an admin PAT and an idle unit.
- `quel-pulse-test` — emit trains of pulses of swept lengths and gaps on every
  tx/trx port, and check on the monitor that each starts where it was put and
  is as long as it was. Needs an admin PAT and an idle unit.
- `quel-measure-delay` — per-port path delay to the monitor. With `--verify`,
  deskew all ports onto a common pulse comb and check each pulse lands where
  intended. Needs an admin PAT and an idle unit.
- `quel-trigger-wait-test` — trigger the units many times at each of a set of
  trigger waits, and report how many runs at each wait completed and why the
  others failed.
- `quel-soak-test` — keep the units busy with random trains of waves on every
  port, for a number of runs or a duration, and tally the runs that fail.
- `quel-unit-config` — `show` / `set` a unit's configuration controls.
  `set` needs an admin PAT and an idle unit.

The tests are also Python functions in `quelware_tools.diagnostics`
(`run_tone_test`, `run_pulse_test`, `run_delay_test`, `run_trigger_wait_test`,
`run_soak_test`).

## Install

```
pip install quelware-tools          # tools only
pip install "quelware-tools[plot]"  # + matplotlib, for the commands that plot
```
