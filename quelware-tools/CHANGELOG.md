# Changelog

## [Unreleased]

### Added

- `quel-soak-test` (`run_soak_test`) — keeps units busy with random trains of waves on every tx/trx port, and random capture windows on every trx port, until a number of runs or a duration is spent, logging how long each step of a run took. Every run goes on all the units at once under one trigger; without `--unit` it runs on every unit the manager knows. A run refused before it starts counts as a pass, tallied by reason; a run that fails, times out or breaks otherwise is a failure, tallied by kind (an instrument failed, a timeout, a unit not reached, the call lost on the way, anything else), and its plan can be saved as JSON and replayed from its seed and run index. The waves of the one port shown in a run start with a 4-tick marker; every other wave is at 0.001 of full scale.

## [0.1.5] - 2026-09-29

### Fixed

- `quel-measure-delay`, `quel-tone-test` and `quel-echo-test` wait for every instrument they trigger with `Session.wait_for_results`, not for the capture alone, so a pulse that was not sent is reported with its cause (e.g. `past_counter`) instead of showing up as a missing or misplaced pulse.

### Changed

- Requires `quelware-client>=0.7.0`, for `Session.wait_for_results`.

## [0.1.4] - 2026-09-15

### Fixed

- `quel-measure-delay --verify` — the comb drive session now takes a 30 s lease instead of the 4 s default, which could expire while the comb was being set up and driven across every port of the unit.

## [0.1.3] - 2026-07-31

### Added

- `quel-tone-test --discard-instruments` — clear the unit's instruments first, so a non-idle unit can be tested.
- `quel-measure-delay --verify-plot-iq DIR` — save the verify comb capture as a PNG plot and a raw `.npy` (implies `--verify`; needs the `plot` extra).

### Fixed

- `quel-tone-test` / `quel-measure-delay` now scope port discovery to `--unit`; they previously used every port the manager reported, which on a multi-unit system could capture from a neighbouring unit's monitor.

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
