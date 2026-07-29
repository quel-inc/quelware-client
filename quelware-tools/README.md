# quelware-tools

Command-line tools and diagnostics for QuEL systems, built on `quelware-client`.

They run against an already-running manager + edge server (endpoint + PAT); they
start nothing themselves.

## Commands

- `quel3-tone-test` — per-port tone test: put the unit's monitor into loopback,
  emit a tone on every tx/trx port, and check it appears in the monitor capture.
  A post-update health check. Exits non-zero if any port fails.
- `quel3-unit-config` — `show` / `set` a unit's configuration controls.
  `set` needs an admin PAT and an idle unit.
- `quel3-echo-test` — emit a pulse on a TRX port and capture the echoed response
  (optionally plotting the I/Q trace; install with the `plot` extra).

## Install

```
pip install quelware-tools          # tools only
pip install "quelware-tools[plot]"  # + matplotlib for quel3-echo-test plots
```
