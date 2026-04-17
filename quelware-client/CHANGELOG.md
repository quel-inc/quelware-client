# Changelog

## [Unreleased]

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
