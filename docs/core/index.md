# Core

`quelware-core` provides the core data models and Protocol Buffer definitions
for QuEL systems: the essential domain entities, gRPC stubs, and serialization
utilities used for internal communication.

!!! note

    This package is an internal dependency of
    [`quelware-client`](../client/index.md). It is installed automatically with
    the client, and general users do not need to install or interact with it
    directly.

## For developers

The gRPC client and protobuf code are generated from `.proto` files using
[buf](https://buf.build/). If you are developing internal services and need to
update the schemas, regenerate the Python files with:

```sh
make generate
```
