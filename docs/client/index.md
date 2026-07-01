# Client

The official Python client library for QuEL systems. It provides a high-level,
asynchronous interface to connect, configure, and orchestrate QuEL systems
over gRPC.

!!! note

    This library currently supports QuEL-3 only. Support for earlier systems
    such as QuEL-1 and QuEL-1 SE is planned for future releases.

## Installation

```sh
pip install quelware-client
```

Optional plotting helpers:

```sh
pip install "quelware-client[plot]"
```

## Authentication

A Personal Access Token (PAT) is required. Set it up in one of the following
ways.

Place it in a config file:

```sh
mkdir -p ~/.config/quelware-client
echo "your-pat-here" > ~/.config/quelware-client/pat
```

Or pass it directly in code:

```python
qc = create_quelware_client("192.0.2.1", 50051, pat="your-pat-here")
```

To obtain a PAT, ask your system administrator to run `quelware-admin user add`
(see [Admin](../admin/index.md)).

## Quick start

!!! note

    The address `192.0.2.1` below is only a placeholder. Set the host and port
    to the control server for your deployment — the correct address depends on
    your environment, so ask your system administrator if you are unsure.

A minimal example of connecting to the control server and managing a session:

```python
import asyncio
from quelware_client import create_quelware_client


async def main():
    qc = create_quelware_client("192.0.2.1", 50051)

    async with qc:
        async with qc.create_session(["your_unit:port_id"]) as session:
            print(f"Session started with token: {session.token}")
            # Deploy instruments, configure the sequencer, and run timelines here.


if __name__ == "__main__":
    asyncio.run(main())
```

For more advanced usage, including pulse generation and sequencer
configuration, see the
[examples directory](https://github.com/quel-inc/quelware-client/tree/main/quelware-client/examples).

## API reference

See the [API Reference](api.md) for the full public interface.
