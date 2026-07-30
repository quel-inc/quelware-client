# Changelog

## [0.4.0] - 2026-07-30

### Added

- `maintenance commission --reset-scope none|control-units|all` selects how much to reset before re-syncing.
- `maintenance inspect` prints per-unit diagnostic measurements.

### Changed

- `maintenance commission --from-scratch` is deprecated; use `--reset-scope all`.

## [0.3.0] - 2026-06-15

### Added

- `unit activate` / `unit drain` / `unit maintain` accept `--all` to apply to every unit in parallel.

### Changed

- `maintenance sync` and `maintenance linkup` are merged into `maintenance commission`.
- Every RPC is now capped at 15s to detect dead servers.
- `maintenance commission` prints progress dots while polling and a per-outcome summary of unit results at the end.

## [0.2.0] - 2026-05-28

### Added

- `maintenance sync` / `maintenance linkup` / `maintenance status` for triggering and polling maintenance jobs.
- `unit list` / `unit status` / `unit activate` / `unit drain` / `unit maintain` for inspecting and managing unit states.

## [0.1.1] - 2026-04-18

### Added

- `--unit-label` flag for `x-unit-label` gRPC metadata (default: `central-server`).

## [0.1.0]

### Added

- Initial release of `quelware-admin`.
