# Changelog

## [Unreleased]

## [0.1.2] - 2026-07-31

### Added

- `quel-measure-delay` — per-port monitor path-delay measurement; `--verify` deskews all ports onto a pulse comb and checks each pulse lands where intended.

## [0.1.1] - 2026-07-30

### Removed

- Unused explicit dependency.

## [0.1.0] - 2026-07-29

### Added

- `quel-tone-test` — per-port tone test: puts the unit's monitor into loopback and checks a tone emitted on each tx/trx port appears in the monitor capture. Exits non-zero if any port fails.
- `quel-unit-config` — `show` / `set` a unit's configuration controls.
- `quel-echo-test` — emit a pulse on a TRX port and capture the echoed response (moved from `quelware-client`; I/Q plotting needs the `plot` extra).
