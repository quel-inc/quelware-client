# Changelog

## [Unreleased]

### Added

- `ignored: bool` field on `ClockUnit` and `MiscellaneousUnit`.

## [0.1.4] - 2026-05-28

### Changed

- Split `ResultContainer.iq_result` into `iq_waveform_result` and `iq_point_result`.
- `GatewayServer.name` is now optional in sysconf.

## [0.1.3] - 2026-05-15

### Added

- `RECEIVER` for protobuf InstrumentRole.
- `DiagnosticsService` proto with `DumpPortState` RPC for human-readable shadow inspection.
- `InstrumentService.TriggerNow` RPC for single-instrument self-timed trigger.

## [0.1.2] - 2026-04-18

### Added

- `STANDBY` status for UnitStatus.
- Go code generation support.

## [0.1.1] - 2026-04-09

### Added

- `AdminService` for access control.
- Unit management methods.

### Removed

- `session_token` field.

## [0.1.0] - 2026-03-30

### Added

- Initial release of `quelware-core`.
