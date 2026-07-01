# Getting started

Install the client, register your token, and run a first measurement with the
bundled example.

## 1. Install

```sh
pip install quelware-client
```

## 2. Register your token

You need a Personal Access Token (PAT), issued by an administrator with
`quelware-admin user add` (see [Admin](admin/index.md)). Save it where the
client looks for it by default:

```sh
mkdir -p ~/.config/quelware-client
echo "your-pat-here" > ~/.config/quelware-client/pat
```

## 3. Run the example

The repository includes a runnable readout example,
[`examples/generate_readout_pulse.py`](https://github.com/quel-inc/quelware-client/blob/main/quelware-client/examples/generate_readout_pulse.py).
Run it against a unit of your system — ask your administrator for the unit label
and the server address:

```sh
python generate_readout_pulse.py quel3-01-028 --host 192.0.2.1 --loopback
```

The `--loopback` flag routes the signal internally, so you can try it without an
external device connected. The script deploys an instrument, plays a pulse,
captures the response, and prints a short summary.

## Next steps

- [Fixed-timeline tutorial](tutorials/fixed-timeline.md) — build the same measurement yourself, step by step
- [Access control](concepts/access-control.md) — roles, sessions, and unit status
