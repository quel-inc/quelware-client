# Changelog

## [Unreleased]

### Added

- `create_session(..., retry_window_ms=20_000)` and `Session(..., retry_window_ms=20_000)`: how long a server that knows the window may keep starting new attempts to open the session while they fail because a resource is in use or a unit answered too late. The first attempt is always made, and an attempt once started is waited for until the call's timeout, the window plus the usual 30 s; opening can take that long. The window must be more than 0 (`ValueError` otherwise); a short one, such as 1, makes one attempt. A server that does not know the window makes one attempt, as before.
- `UnitUnreachableError`: opening a session raises it when the server could not reach a unit or a unit answered too late, with `unit_labels` naming the unit. It is a `QuelwareClientError`, which was raised before. An `UNAVAILABLE` that names no unit, such as when the server itself cannot be reached, is still a plain `QuelwareClientError`.

### Changed

- With a server that knows the retry window, `create_session` lets it retry opening the session for 20 s by default. Opening a resource another session keeps fails after that window, where it failed after about a second before; pass `retry_window_ms=1` to fail at once. With a server that does not know the window, opening fails as before, but may take up to 50 s instead of 30 s before it times out.
- `create_session` and `Session` default to `ttl_ms=5000` and `tentative_ttl_ms=5000`, up from 4000 and 1000. Opening a session that spans several units fails less often when a unit answers slowly, because the tentative locks held while opening last long enough to be committed. A session left without `extend` now lasts 5 s instead of 4 s.
- Breaking for a `SessionAgent` implemented outside the client: `open_session` takes `retry_window_ms`, which `Session` passes, so such an implementation needs to accept it.
- Configuring a timeline sends its waveforms as bytes (`DenseIqArray`) to a unit whose version names `dense_waveform`, and as samples to any other unit. A unit parses the bytes far faster, so it keeps answering other calls while it takes a long timeline. The client reads each unit's version once, when it starts; a unit that does not answer is taken as old.
- `WorkerAgent.get_version` returns the unit's `UnitVersion` (its version and the features it names that the client knows), or None when the unit does not answer. `UnitVersion.supports("dense_waveform")` says whether the unit named a feature, and raises `ValueError` for a name the client does not know. `AgentContainer.unit_version` holds what the client read at start.
- `InstrumentAgentGrpc(..., use_dense_waveforms=True)` sends waveforms as bytes. The default agents are built so for a unit whose version names `dense_waveform`: the client now reads the versions before it builds the instrument agents. `InstrumentAgent` itself is unchanged.

## [0.7.4] - 2026-11-02

### Added

- `Session.abort_runs()`, which stops the session's runs on every unit, before the trigger time or part way through. A run stops as a whole, because its instruments share the unit's waveform generators and captures, so it takes no instruments. Waiting for an instrument of a run raises the server's abort error. `AbortFailedError` is raised, once every unit has been asked, when some units failed; `failures` holds the error of each, by unit.
- `UnitBusyError` is raised also by `Session.abort_runs` while a trigger or initialize of the session is running, and by a trigger or initialize while `abort_runs` is.

## [0.7.3] - 2026-10-01

### Added

- `examples/fixed_timeline.py`, the code of the fixed-timeline tutorial as a script you can run against a system. The docs quote it, and the lint and the type check cover it, so it keeps up with the API.
- `NotTriggeredError`: `Session.wait_for_results`, `Session.wait_for_result`, `Session.fetch_result` and the same methods of `InstrumentDriver` raise it immediately if an instrument was not in the last trigger on its unit. Before, the request went to the unit, which could hang (armed but not triggered), return an empty result, or fail with `INTERNAL`. Within a session, each unit has at most one run: a new trigger on the unit replaces it, and initializing an instrument on the unit clears it. Other sessions on the unit have their own runs.
- `UnitBusyError`: `Session.trigger` and `Session.initialize` raise it immediately if a trigger or initialize of the same session is already running on the unit.
- `InitializeFailedError`: `Session.initialize` raises it, once every unit has finished, when some units failed; `failures` holds the error of each, by unit.
- `Session.initialize(instrument_ids, parallel=True)`, which initializes the units at the same time, or one after another when not `parallel`, and every unit also after one fails, `Session.fetch_result(instrument_id)` and `Session.wait_for_result(instrument_id, timeout_sec=None)`. The `InstrumentDriver` methods of the same names now call them, so the session knows which instruments can be waited for.

### Changed

- `InstrumentDriver` requires the `session` it belongs to. `create_instrument_driver_fixed_timeline` passes it, so only code that builds a driver directly needs a change.
- `InstrumentAgent.apply` is renamed `arm`, because it arms the instruments (`InstrumentDriver.apply` configures an instrument). It still calls the `Apply` RPC.

## [0.7.2] - 2026-09-29

### Changed

- Every call has a deadline: 30 s, or 120 s to configure a unit, and a trigger through the manager the wait it asks for longer. A unit that is gone fails a call instead of holding it until a proxy gives up, which was 600 s. A fetch waits 60 s at a time and is made again past it, so a long run is still waited for; how long in all is still up to `wait_for_results(timeout_sec=...)`.
- The health check gives a unit 10 s to answer, and takes one that does not, or whose connection cannot be made, as not healthy, instead of waiting on it.

## [0.7.1] - 2026-09-29

### Changed

- The client-side fallback trigger of a single unit passes `wait_ms` (raised to 500 ms) to the unit, which used to fire after its own fixed 150 ms whatever was asked. `InstrumentAgent.trigger_now` takes `min_wait_ms`.
- `InstrumentAgentGrpc.initialize`, `configure`, `apply` and `trigger_now` are retried when their connection is lost, as when a proxy closes it after an hour: making any of them again leaves the unit as the first did. `schedule_trigger` is not, since a late one would start the run past its count.
- Requires `quelware-core>=0.9.0`, for `TriggerNowRequest.requested_min_wait_ms`.

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
