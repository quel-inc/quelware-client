# Changelog

## [Unreleased]

## [0.1.9] - 2026-11-20

### Added

- `quelware_tools.diagnostics.correctness` (`Judge`, `judge`) judges whether what came back is what was sent, from the shots alone (`quelware_tools.diagnostics.shots`): each port's path delay is measured once, by a shot that measures it (`delay_shot`), and every later shot along the path is held to it; a shot's gain along each path is estimated from all of its pulses, and every pulse is held to the gain, phase and position it was sent with; a window holds nothing else but the noise its iterations average down; shots along one path share its gain, and the same shot fired again comes back the same. A shot along a path whose delay was not measured is a problem. A pulse too short to measure is not judged by itself, and one with no silence around it is not held to its position. A raw shot's mean is judged so, and each of its iterations as well: every pulse is held to the gain and phase of its median iteration, and the window between the pulses to one iteration's noise.
- `quel-soak-test --check-monitor` (`run_soak_test(check_monitor=True)`) puts the units in monitor loopback, after discarding every instrument on them, and back in open mode at the end. Each run shows one port of each unit, at full scale throughout its waves, while every other port sends waves of nothing; the windows are captured on each unit's monitor, and what it captured is judged against the shown port's waves (within `tolerance`). Before the runs, it measures each port's delay to its monitor, one port of each unit at a time, and stops with a failure of kind `delay` if one cannot be measured. A run that comes back otherwise than it was sent is a failure of kind `wrong`. Needs an admin PAT.
- `quel-soak-test` returns every iteration, rather than their mean, in a share of its runs (`SoakProfile.raw_share`, a quarter by default), repeated fewer times (`SoakProfile.raw_iterations`), with the windows of such a run summed over its iterations within `SoakProfile.max_raw_capture_ns` (40 µs by default), so that returning them keeps the units answering. With `--check-monitor`, each iteration of such a run is judged.
- `quel-soak-test --timings PATH` (`run_soak_test(timings_path=...)`) writes to `PATH`, as JSON, the version of its layout (`format`), the units and ports it ran on, its settings, the versions of quelware-tools and quelware-client, and each run's timing: when it began, the seconds each step took (initialize, configure, trigger, wait; a failed run up to the step it failed in), its waves, iterations, whether it was raw, and the kind of its failure. It is written at the end, also when interrupted. `SoakReport.timings` holds the same timings (`RunTiming`).
- `quel-soak-compare A B` (`compare_soak_timings`) compares two such files: for each step and for the whole run, the median, the 95th percentile and the longest over the runs that completed in each, and, when both drew the same runs (the same seed, kinds and ports, whatever the frequency or other settings that do not change what is drawn), the median of each run's difference, B minus A. When the runs are of several kinds, it also compares the runs of each kind drawn in both. A and B are named after their files, or as `--label-a` and `--label-b` say.
- `quel-soak-test` runs a round of kinds (`DEFAULT_ROUND`, `RoundEntry`, `round_order`, `draw_run`), after the loads a client such as qubex sends: the light kinds many times and the heavy ones a few times at their heaviest, each kind's runs spread over the round and the heavy ones apart. A round is 20 runs each of `sparse`, the runs it drew before, `spectroscopy` (`SPECTROSCOPY_PROFILE`), capture windows up to 8.3 µs long repeated 1024 ns apart, and `dense-cr` (`DENSE_CR_PROFILE`), flat pulses of 1 µs and 4 µs; 4 runs of `packed-sweep` (`PACKED_SWEEP_PROFILE`), 50 points of a few short pulses and a readout in one trigger; and 2 runs each of `packed-rb-1024` and `packed-rb-2048` (`PACKED_RB_PROFILE`), 30 randomized benchmarking sequences of that many gates, pulses 12.8 ns or 25.6 ns long, each followed by a readout and a 153.6 µs blank, in one trigger, so tens of thousands of events per port. The packed kinds read out for 512 ns, as qubex does by default, and run as many iterations in one trigger as qubex does, which splits 1024 shots so that a readout port captures at most 15 million samples in a trigger: 512 for packed-rb and 342 for packed-sweep. `SoakProfile.jobs`, `job_blank_ticks` and `readout_ticks` lay such packed runs. `--kind` keeps only the kinds named in the round. `--detune-hz` (`run_soak_test(detune_hz=...)`) sets every instrument that far off the carrier it is deployed at, so the units modulate what they send and demodulate what they capture, which `--check-monitor` then judges. Each run's kind is in its plan and its timing. `run_soak_test(profile=...)` takes one `SoakProfile`, whose runs are drawn as before, or a round.

### Changed

- `quel-soak-test` stops after one round by default (68 runs), rather than running until interrupted. `--rounds`, `--runs` and `--duration-sec` set how long it runs, and it stops at whichever of those given comes first; `--duration-sec` alone runs for that long, and `--runs 0` runs until interrupted. `run_soak_test` draws a round of kinds by default (`DEFAULT_ROUND`), rather than the runs of `DEFAULT_PROFILE`; pass `profile=DEFAULT_PROFILE` for those.
- Requires `quelware-client>=0.8.0`, which reads the values a server built with `quelware-core>=0.10.0` returns.

## [0.1.8] - 2026-11-02

### Added

- `quel-recover-past-counter` (`run_recover_past_counter`) brings a unit back to normal after a run that failed with `past_counter`, without a reboot. A temporary workaround, until an update of the units makes it unnecessary: it triggers every port a few seconds ahead and cancels the run on purpose before it starts. It replaces the instruments on every port of the units and removes them at the end.

### Changed

- Requires `quelware-client>=0.7.4`, for `Session.abort_runs`.
- `quel-trigger-wait-test` no longer reports a trigger time per wait: it was the median of the client's wall time of `Session.trigger`, arming included, which says nothing about whether a run starts in time. Each run's time is logged instead, and `WaitResult.trigger_sec` is gone.

## [0.1.7] - 2026-10-01

### Added

- `quel-soak-test --initialize-each-run` (`run_soak_test(initialize_each_run=True)`) initializes the instruments at the start of every run, before it configures them, as a client that starts each run afresh does, and logs how long it took.

### Changed

- Requires `quelware-client>=0.7.3`, for `Session.initialize`.

## [0.1.6] - 2026-09-29

### Added

- `quel-trigger-wait-test` (`run_trigger_wait_test`) — puts a transmitter sending one short pulse on every tx/trx port of the units and triggers them all at once, a number of times at each of a set of waits between the trigger and the start (150 to 600 ms by default), one wait after another in turn, and reports for each wait how many runs completed and what the others failed on (`past_counter`, another unit error, or the call's error). One unit is triggered by itself, several through the manager; the server raises a wait under its 150 ms floor to the floor.
- `quel-pulse-test` (`run_pulse_test`) — for every tx/trx port of a unit, emits a train of rectangular pulses of swept lengths and gaps, around the ones where the server merges waves into one send or splits them, and checks on the monitor in loopback that each pulse starts where it was put, counting from the first, and is as long as it was, within a tolerance, and that no other pulse shows up. Pulses with no gap between them are one. `--plot-iq DIR` saves each port's capture there as a PNG plot, one row per run of pulses with the expected and the seen ones marked, and as a raw `.npy` (needs the `plot` extra).
- `quel-soak-test` (`run_soak_test`) — keeps units busy with random trains of waves on every tx/trx port, and random capture windows on every trx port, until a number of runs or a duration is spent, logging how long each step of a run took. Every run goes on all the units at once under one trigger; without `--unit` it runs on every unit the manager knows. A run refused before it starts counts as a pass, tallied by reason; a run that fails, times out or breaks otherwise is a failure, tallied by kind (an instrument failed, a timeout, a unit not reached, the call lost on the way, anything else), and its plan can be saved as JSON and replayed from its seed and run index. The waves of the one port shown in a run start with a 4-tick marker; every other wave is at 0.001 of full scale.

### Changed

- Requires `quelware-client>=0.7.2`: `quel-trigger-wait-test` needs a single unit to be passed the wait asked for (0.7.1), and a run on a unit that is gone to fail instead of hanging (0.7.2).

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
