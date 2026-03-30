# quelware-client

The official Python client library for QuEL-3, an integrated control system for quantum computing developed by [QuEL, inc.](https://quel-inc.com/)

It provides a high-level, asynchronous interface to connect, configure, and orchestrate QuEL systems via gRPC.

Note: Currently, this library supports QuEL-3.
We plan to expand support to our earlier models, such as QuEL-1 and QuEL-1 SE, in future releases.

## Installation

You can easily install the package via pip:

```sh
pip install quelware-client
```

## Quick Start

Here is a minimal example of connecting to the control server in QuEL system and managing an session:

```python
import asyncio
from quelware_client import create_quelware_client

async def main():
    qc = create_quelware_client(<hostname>, <port>)

    async with qc:
        async with qc.create_session(["your_unit:port_id"]) as session:
            print(f"Session started with token: {session.token}")
            # Deploy instruments, configure sequencer, and run timelines here...

if __name__ == "__main__":
    asyncio.run(main())
```

For more advanced usage, including pulse generation and sequencer configuration, please check the [examples directory](./tree/main/quelware-client/examples).

## Documentation

For full API reference and advanced guides, visit the [official documentation](https://quel-inc.github.io/quelware-client/).

## License

This project is licensed under the Apache License 2.0.
