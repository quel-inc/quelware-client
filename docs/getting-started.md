# Getting started

Install the client, register your token, and run a first measurement with
`quelware-tools`.

## 1. Install

```sh
pip install quelware-client quelware-tools
```

## 2. Register your token

You need a Personal Access Token (PAT), issued by an administrator with
`quelware-admin user add` (see [Admin](admin/index.md)). Save it where the
client looks for it by default:

```sh
mkdir -p ~/.config/quelware-client
echo "your-pat-here" > ~/.config/quelware-client/pat
```

## 3. Run the echo test

[`quel3-echo-test`](tools/index.md) emits a pulse on a transceiver port and
captures the echoed response. Run it against your system — ask your
administrator for the server address:

```sh
quel3-echo-test 192.0.2.1 --loopback
```

The `--loopback` flag routes the signal internally, so you can try it without an
external device connected. It deploys an instrument, plays a pulse, captures the
response, and prints a short summary.

## Next steps

- [Tools](tools/index.md) — the rest of the command-line tools
- [Fixed-timeline tutorial](tutorials/fixed-timeline.md) — build a measurement yourself, step by step
- [Access control](concepts/access-control.md) — roles, sessions, and unit status
