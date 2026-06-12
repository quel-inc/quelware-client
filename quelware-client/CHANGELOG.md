# Changelog

## [Unreleased]

## [0.4.0]

### Added

- `Session.extend(new_ttl_ms)` to extend an active session via `SessionService.ExtendSession` RPC.
- `SessionAgent.extend_session` Protocol method.

## [0.3.0] - 2026-06-09

### Added

- `Session.trigger` now routes through the manager by default (single round-trip, shorter lead).
- `ServiceUnavailableError` exception for catching cases where the server-side service is not available.

### Changed

- `Session.trigger` default `wait_ms` changed from `400` to `None`.
- `Session.trigger` returns the scheduled clock count (`int`).
- Default multi-unit trigger offset is 0 ticks (was 16).

### Removed

- `agent.instrument(unit).get_clock_snapshot()` — use `agent.worker(unit).get_clock_snapshot()`.

## [0.2.0] - 2026-05-28

### Changed

- Follow `ResultContainer` rename: callers now use `iq_waveform_result` or `iq_point_result`.

### Added

- gRPC calls automatically retry on transient connection drops (e.g. `Connection lost`).

## [0.1.4.post1] - 2026-05-18

### Fixed

- Bump `quelware-core` floor to `>=0.1.3`.

## [0.1.4] - 2026-05-15

### Added

- `QuelwareClient.dump_port_state(port_id)` for fetching a human-readable shadow dump of a port. Output is for visual inspection only; format is unstable.

### Changed

- `Session.trigger` uses the new `TriggerNow` RPC for single-instrument triggers to avoid the clock snapshot round-trip.

## [0.1.3] - 2026-04-20

### Changed

- Parallelize health checks during initialization.
- Rewrite examples.

## [0.1.2] - 2026-04-18

### Added

- Unit-prefixed instrument alias (`{unit_label}:{alias}`) to prevent cross-unit alias collisions.
- `unit` parameter in `InstrumentResolver.find_inst_info_by_alias()` for disambiguation.

### Changed

- Skip unhealthy units during initialization instead of raising an error.

## [0.1.1] - 2026-04-09

### Added

- Check connection when starting QuelwareClient.
- Ensure that target resources are locked when opening a session.
- Set Personal Access Token (PAT) in metadata.

### Changed

- Use gRPC metadata to pass the `session_token` to the servers.

## [0.1.0] - 2026-03-30

### Added

- Initial release of `quelware-client`.
- Support for connecting to QuEL-3 integrated control system via gRPC.
- Asynchronous session management and instrument configuration.
- Basic examples for generating readout pulses.
