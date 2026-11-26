# klipper_tmc_autotune hybrid: measured chopper, computed everything else

[Versione italiana](HYBRID_IT.md)

This fork of [klipper_tmc_autotune](https://github.com/andrewmcgr/klipper_tmc_autotune)
can take the spreadCycle chopper registers **measured** on your printer by
[chopper-autotune](https://github.com/anton-vinogradov/chopper-autotune)
instead of the ones **computed** from the motor database. Everything else is
still tuned by autotune, as upstream does.

| What | Who decides it |
|---|---|
| `tbl`, `toff`, `hstrt`, `hend`, `tpfd` | chopper-autotune (accelerometer measurement) |
| StealthChop / PWM (`pwm_grad`, `pwm_ofs`, `pwm_freq`) | autotune (motor model) |
| CoolStep, StallGuard thresholds | autotune |
| TMC2240 `slope_control`, high-speed fullstep | autotune |
| `run_current` | you (chopper-autotune's `CHOPPER_CURRENT` can help) |

> Status: unit-tested (`tests/test_hybrid.py`, 19 tests, Klipper mocked).
> Not yet validated on real hardware. Use at your own risk and keep a config backup.

## What changes compared to upstream

1. New option `measured_chopper: True` in `[autotune_tmc ...]`. It reads
   `driver_TBL`, `driver_TOFF`, `driver_HSTRT`, `driver_HEND` and `driver_TPFD`
   from the matching `[tmc... ...]` section: the lines `CHOPPER_TUNE SAVE=1` writes.
2. New options `hstrt` and `hend` for manual hysteresis (set both or neither).
3. Priority: measured, then manual, then computed.
4. Every chopper set is checked against the datasheet limits **before** any
   driver write. An invalid set stops Klipper with a clear message.
5. Two fixes discussed in upstream issue #339: `TOFF=1` now requires `TBL>=2`
   (it used to accept 1), and the fallback clock of TMC2208/2209 is 12 MHz
   (it was 12.5 MHz).
6. `AUTOTUNE_TMC` accepts `HSTRT=`, `HEND=` and `MEASURED=0|1`, and always
   replies with the values applied and where they came from.
7. `printer["autotune_tmc stepper_x"]` exposes the applied values and their
   `source`, for use in macros.

## Installation

### New install (autotune not installed yet)

Clone into a folder named `klipper_tmc_autotune`: the install script looks for that name.

```bash
cd ~ && git clone -b hybrid https://github.com/quser01/klipper_tmc_autotune_hybrid.git klipper_tmc_autotune
bash ~/klipper_tmc_autotune/install.sh
```

Then follow upstream's README to add the `[autotune_tmc ...]` sections.

### Switching an existing autotune install to this fork

1. Make sure the folder has no local changes:

    ```bash
    cd ~/klipper_tmc_autotune
    git status
    ```

    It must say `nothing to commit, working tree clean`. If it lists modified
    files, sort them out first or the next step fails.

2. Point the folder to the fork and switch to the `hybrid` branch:

    ```bash
    git remote set-url origin https://github.com/quser01/klipper_tmc_autotune_hybrid.git
    git fetch origin
    git checkout -B hybrid origin/hybrid
    ```

    No need to run `install.sh` again: Klipper's links already point to this folder.

### Moonraker updates

In `moonraker.conf`:

```ini
[update_manager klipper_tmc_autotune]
type: git_repo
channel: dev
path: ~/klipper_tmc_autotune
origin: https://github.com/quser01/klipper_tmc_autotune_hybrid.git
primary_branch: hybrid
managed_services: klipper
install_script: install.sh
```

With an existing install you only need to change `origin` and `primary_branch`.

### Restart and check

`RESTART` is not enough: it does not reload Python code.

```bash
sudo systemctl restart moonraker
sudo systemctl restart klipper
grep -c measured_chopper ~/klipper_tmc_autotune/autotune_tmc.py   # must be > 0
```

Klipper must start without errors. At this point it still behaves like
upstream autotune: the measured chopper is only used after the steps below.

## Measuring the chopper

The measurement must run with autotune **off** on the motors being measured:
chopper-autotune refuses to save on a motor managed by autotune, and
autotune's CoolStep would lower the current during the measurement.

1. Install chopper-autotune (once; Klipper restarts at the end):

    ```bash
    cd ~ && git clone https://github.com/anton-vinogradov/chopper-autotune && bash ./chopper-autotune/install.sh
    ```

2. Comment out (`#`) every line of the `[autotune_tmc ...]` sections of the
   motors to tune, usually X and Y (`stepper_x`, `stepper_y`, plus
   `stepper_x1` and `stepper_y1` on AWD). Leave Z and the extruder as they are.
3. **Only with sensorless homing on those axes:** add the StallGuard threshold
   autotune used to the `[tmc...]` section (`driver_SGT` on TMC5160, TMC2240
   and TMC2130; `driver_SGTHRS` on TMC2209), with the value of autotune's
   `sgt` / `sg4_thrs` (defaults 1 / 40). Without it, homing may not stop.
4. Restart Klipper, then `G28`. With two motors on one axis the nozzle must be
   at least 5 mm above the bed: `G1 Z10` if needed.
5. Dry run, moves nothing:

    ```
    CHOPPER_TUNE DRY_RUN=1
    ```

    Read what it prints (drivers, moves, distance from the edges, heat
    warnings) and fix any problem it reports.
6. Measure and save:

    ```
    CHOPPER_TUNE SAVE=1
    ```

    It takes about 20 minutes. On AWD every X/Y motor stays powered for the
    whole run: keep an eye on driver temperatures. At the end the tool writes
    the `driver_*` lines into the `[tmc...]` sections and restarts Klipper,
    which clears homing.
7. Check that the `[tmc...]` sections of the tuned motors have the new
   `driver_*` lines. The full log is in
   `~/printer_data/config/chopper-autotune/tune.log`.

## Turning autotune back on with the measured chopper

Uncomment the `[autotune_tmc ...]` sections and add `measured_chopper: True`
to each one:

```ini
[autotune_tmc stepper_x]
motor: <your motor>
voltage: <your supply voltage>
measured_chopper: True
```

- Remove `tbl`, `toff`, `tpfd`, `hstrt` and `hend` from these sections if
  present: with `measured_chopper` on, Klipper stops if it finds them.
- Keep the `driver_*` lines in the `[tmc...]` sections: autotune now reads the
  chopper from there.
- A `driver_SGT` added in step 3 can stay: autotune overwrites it with its own
  `sgt` at start.

Then `RESTART` (enough here, the code did not change) and `G28`.

## Checking and comparing

Run, for every tuned motor:

```
AUTOTUNE_TMC STEPPER=stepper_x
```

The reply appears in the Mainsail or Fluidd console, right below the command:

```
autotune stepper_x: chopper measured tbl=1 toff=3 tpfd=0 hstrt=2 hend=4
```

- It must say `measured`. If it says `computed`, `measured_chopper: True` is
  not active on that motor.
- The numbers must match the `driver_*` lines of that motor's `[tmc...]` section.

The same values are in `klippy.log`, written at every Klipper start. Search
for `chopper` to find lines such as
`autotune_tmc stepper_x chopper {'tbl': 1, 'toff': 3, ..., 'source': 'measured'}`.
Useful when Klipper does not start and the console is not available.

**A/B comparison.** Always switch **all** motors of the same axis together:
two motors of one axis with different choppers work against each other.

```
AUTOTUNE_TMC STEPPER=stepper_x MEASURED=0
AUTOTUNE_TMC STEPPER=stepper_x1 MEASURED=0
```

Print the same test part with `MEASURED=0` and with `MEASURED=1` and compare
noise and surfaces. The switch lasts until the next restart.

## Going back, re-measuring, common problems

- **Back to the computed chopper:** remove `measured_chopper: True`, then `RESTART`.
- **Back to upstream autotune:** `git -C ~/klipper_tmc_autotune checkout main`,
  set `origin` back to `https://github.com/andrewmcgr/klipper_tmc_autotune.git`
  and `primary_branch: main` in `moonraker.conf`, then
  `sudo systemctl restart klipper`.
- **Re-measure** after changing motors, voltage, current or belt tension:
  repeat from "Measuring the chopper".

| Message or symptom | Cause | Fix |
|---|---|---|
| `measured_chopper is on, but [tmc... stepper_x] has no driver_TBL` | The measurement was not saved for that motor | Measure again with `SAVE=1` |
| `measured_chopper takes the chopper from ..., remove tbl` | Chopper values also in the autotune section | Remove them from `[autotune_tmc]` |
| `measured chopper invalid, toff=1 requires tbl >= 2` | `driver_*` lines edited by hand into an invalid set | Measure again or fix the values |
| `not saving ...: autotune resets its chopper at start` | `[autotune_tmc]` still active during the measurement | Comment it out and measure again |
| `computed PWM_OFS=... leaves no headroom` | PWM math out of range at your voltage and current | Lower `run_current` |
| X/Y homing does not stop | Sensorless homing without a StallGuard threshold while autotune is off | Stop the printer and add `driver_SGT` (measuring, step 3) |
| Motor whines after tuning | Chopper frequency in the audible band | `CHOPPER_TUNE SAVE=1 SKIP_AUDIBLE=1` |

## Known limits

- The measurement runs **without CoolStep** (full current); when printing,
  autotune turns CoolStep back on, which lowers the current at light load.
  Autotune's own model also computes hysteresis at full current, so the
  assumption is the same, but it has not been verified by measurement.
- chopper-autotune minimises the low-frequency vibration the accelerometer
  sees, not perceived loudness, and it does not test very low speeds (5 to 10 mm/s).
- On an axis with two motors `CHOPPER_TUNE` works, but `CHOPPER_CURRENT` and
  the map step do not yet (chopper-autotune issue #129).

## Keeping the fork in sync (maintainer)

1. On GitHub, on `main`: **Sync fork → Update branch**.
2. Open a pull request inside the fork with base `hybrid` and compare `main`, then merge it.
3. If GitHub reports **Can't automatically merge**, upstream changed the same
   lines: resolve the conflict by hand instead of forcing it.

## Credits

- [klipper_tmc_autotune](https://github.com/andrewmcgr/klipper_tmc_autotune)
  by andrewmcgr and contributors, GPL-3.0. This fork keeps that license.
- [chopper-autotune](https://github.com/anton-vinogradov/chopper-autotune) by
  anton-vinogradov, MIT. Not included here: install it separately.
