# Tools

`quelware-tools` is a set of command-line tools and diagnostics for QuEL
systems, built on [`quelware-client`](../client/index.md). They run against an
already-running manager and edge server — you give them an endpoint and a PAT;
they start nothing themselves.

## Install

```sh
pip install quelware-tools          # tools only
pip install "quelware-tools[plot]"  # + matplotlib, for quel-echo-test plots
```

## Authentication

Each command takes a PAT (see [Access control](../concepts/access-control.md)).
It defaults to the PAT configured for `quelware-client`; override it with
`--pat`.

## Commands

### `quel-tone-test`

Per-port tone test: puts the unit's monitor into loopback, emits a tone on every
tx/trx port, and checks it appears in the monitor capture. A health check after
an on-site software update; exits non-zero if any port fails.

```sh
quel-tone-test <host> --unit <label>
```

### `quel-measure-delay`

Per-port path delay: puts the monitor into loopback and, one tx/trx port at a
time, emits a pulse while capturing from t=0 to time its arrival. With
`--verify`, deskews every port onto a common pulse comb, emits them together, and
checks each pulse lands where intended. Requires an administrator PAT and an idle
unit.

```sh
quel-measure-delay <host> --unit <label>
quel-measure-delay <host> --unit <label> --verify
```

### `quel-unit-config`

Show or set a unit's configuration controls.

```sh
quel-unit-config show <host> --unit <label>
quel-unit-config set <host> --unit <label> KEY=VALUE
```

`set` requires an administrator PAT and an idle unit (no deployed instruments).

### `quel-echo-test`

Emit a pulse on a TRX port and capture the echoed response, optionally plotting
the I/Q trace (needs the `plot` extra).

```sh
quel-echo-test <host> --iq-plot
```
