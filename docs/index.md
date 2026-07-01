# quelware-client

Client libraries and tools for **QuEL systems**, integrated control systems for
quantum computing developed by [QuEL, Inc.](https://quel-inc.com/)

This site documents the packages in the
[`quelware-client`](https://github.com/quel-inc/quelware-client) monorepo.

!!! note

    These libraries currently support **QuEL-3** only. Support for earlier
    systems, such as QuEL-1 and QuEL-1 SE, is planned for future releases.

## Packages

<div class="grid cards" markdown>

-   :material-code-braces-box: **[Client](client/index.md)**

    ---

    The Python client library for connecting to QuEL systems over gRPC.
    Start here if you are writing experiment code.

-   :material-console: **[Admin](admin/index.md)**

    ---

    A command-line tool for managing users on a QuEL system.
    Intended for administrators.

-   :material-cube-outline: **[Core](core/index.md)**

    ---

    Shared data models and Protocol Buffer definitions. An internal
    dependency of the client — most users never use it directly.

</div>

## Installation

```sh
pip install quelware-client
```

`quelware-core` is installed automatically as a dependency.

## License

All packages are licensed under the
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

