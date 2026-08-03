# quelware-core

**Note**: This is an internal dependency for the other quelware packages.
General users do not need to install or interact with it directly.

The core data models and Protocol Buffer definitions for QuEL systems, integrated control systems for quantum computing developed by [QuEL, inc.](https://quel-inc.com/)

It provides the essential domain entities, gRPC stubs, and serialization utilities required for the internal communication.

## Layout

- `proto/` — the Protocol Buffer definitions, the source of truth for both bindings
- `python/` — the Python package, published to PyPI as [quelware-core](https://pypi.org/project/quelware-core/) and installed automatically with `quelware-client`
- `go/` — the generated Go bindings, consumed by `quelware-admin` via a local module replace

The generated code is not checked in. After a fresh clone, `go/quelware/` does not exist at all and `python/src/quelware_core/pb/` is missing from the Python package, until you run `make generate`.

## Documentation

See the [core documentation](https://quel-inc.github.io/quelware-client/core/). The full site is at <https://quel-inc.github.io/quelware-client/>.

## For Developers

The gRPC stubs and protobuf codes are generated from the `.proto` files using buf.

Run the following after a fresh clone, and again whenever you update the .proto schemas:

```sh
make generate
```

To regenerate only one language, use `make generate-python` or `make generate-go`.

## License

This project is licensed under the Apache License 2.0.
