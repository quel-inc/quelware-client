# Changelog

## [Unreleased]

### Added

- `TriggerNowRequest.requested_min_wait_ms`: how long from now a single unit's self-timed trigger fires, as `TriggerRequest.requested_min_wait_ms` does across units.

## [0.8.0] - 2026-09-26

### Changed

- `betterproto2` and `betterproto2_compiler` move to 0.10.

### Deprecated

- `quelware_core.entities.sysconf` warns on import, and will be removed.

## [0.7.0] - 2026-08-26

### Added

- `DenseIqArray` / `DenseWaveformList`: waveform payloads as a typed array carried in `bytes`, removing the per-sample `repeated double` encoding cost on large fetches.

### Changed

- Waveform results are serialized as `IqResult.dense_waveforms`; the legacy `WaveformList` form is still parsed, so a new client keeps working against an old backend.

## [0.6.0] - 2026-08-07

### Changed

- `InstrumentStatus` replaces `UNCONFIGURED` and `CONFIGURED` with a single `IDLE`.

### Added

- `InstrumentStatus.FAILED` on the wire.
- `InstrumentStatus.ABORTED`.
- `InstrumentService.Abort` RPC to stop a run in flight.

### Fixed

- `GetStatus` raised `KeyError` for `CONFIGURED` and `FAILED`.

## [0.5.0] - 2026-07-27

### Added

- `WorkerService.ConfigureUnit` / `GetUnitConfiguration` RPCs to view and change unit-wide settings.
- `ResourceService.DiscardInstruments` RPC to undeploy the instruments on a port.
- `SyncResetScope` enum and `StartCommissionRequest.reset_scope` to select how much to reset before commissioning: none, control units only, or all.
- `MaintenanceService.Inspect` RPC returning per-unit diagnostic measurements as opaque key/value strings.

### Changed

- `StartCommissionRequest.preserve_healthy` is deprecated in favor of `reset_scope`; it is still honored when `reset_scope` is unspecified (true maps to none, false to all).

## [0.4.0] - 2026-06-15

### Changed

- `MaintenanceService` replaces `StartTimeSync` / `StartLinkup` with a single `StartCommission` RPC (with `preserve_healthy` flag). `JobKind` now has only `COMMISSION`.

## [0.3.0] - 2026-06-12

### Added

- `SessionService.ExtendSession` RPC for extending the TTL of an active session.

## [0.2.0] - 2026-06-09

### Added

- `ignored: bool` field on `ClockUnit` and `MiscellaneousUnit`.
- `TriggerService` proto with `Trigger` RPC for manager-side trigger orchestration.
- `WorkerService.GetClockSnapshot` RPC for clock snapshot retrieval by the manager.

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
