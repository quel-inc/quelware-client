# Changelog

## [Unreleased]

### Changed

- The client-side fallback trigger of a single unit passes `wait_ms` (raised to 500 ms) to the unit, which used to fire after its own fixed 150 ms whatever was asked. `InstrumentAgent.trigger_now` takes `min_wait_ms`.
- `InstrumentAgentGrpc.initialize`, `configure`, `apply` and `trigger_now` are retried when their connection is lost, as when a proxy closes it after an hour: making any of them again leaves the unit as the first did. `schedule_trigger` is not, since a late one would start the run past its count.

## [0.7.0] - 2026-09-29

### Added

- `Session.wait_for_results(instrument_ids, timeout_sec=None)` waits until every instrument given to `trigger()` has completed its run and returns each one's result. When any of them failed, it raises `RunFailedError` once all have finished, holding each failure and the results of the others; waiting for the capturing instruments alone misses a failure of the ones that only send.

## [0.6.1] - 2026-08-18

### Changed

- `Sequencer` now inserts a blank period between iterations when the timeline repeats. The length defaults to 2000 ns and is configurable via the new `iter_blank_ns` constructor parameter.
- `Sequencer.aligned_length_fs` property is replaced by the `Sequencer.get_aligned_length_fs(post_blank_fs=0)` method, which can account for a trailing blank.

## [0.6.0] - 2026-08-07

### Changed

- Bump `quelware-core` floor to `>=0.6.0`.

## [0.5.1] - 2026-07-30

### Fixed

- Bump `quelware-core` floor to `>=0.5.0`.

## [0.5.0] - 2026-07-29

### Added

- `QuelwareClient.get_unit_configuration(unit_label)` to read a unit's supported controls and their current values.
- `Session.configure_unit(unit_label, controls)` to change a unit's controls.
- `Session.discard_instruments(port_id)` to remove the instruments deployed on a port.

### Removed

- The `quel3-echo-test` command — command-line tools now ship in the separate `quelware-tools` package, so `quelware-client` no longer depends on `typer` or provides the `plot` extra.

## [0.4.1] - 2026-06-17

### Added

- `InstrumentDriver.wait_for_result(timeout_sec=None)` blocks until the result is ready, transparently absorbing server-side fetch timeouts.

## [0.4.0] - 2026-06-12

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
