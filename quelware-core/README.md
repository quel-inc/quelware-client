# quelware-core

**Note**: This package is an internal dependency for quelware-client.
General users do not need to install or interact with this package directly.

The core data models and Protocol Buffer definitions for QuEL system.

It provides the essential domain entities, gRPC stubs, and serialization utilities required for the internal communication and is automatically installed when you install quelware-client.

## For Developers

The gRPC client and protobuf codes are generated from .proto files using buf.

If you are developing internal services and need to update the .proto schemas, you can regenerate the Python files by running:

make generate

## License

This project is licensed under the Apache License 2.0.
