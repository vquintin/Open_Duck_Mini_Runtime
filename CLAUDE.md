# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The on-robot runtime for Open Duck Mini v2, a small bipedal robot: a Raspberry Pi Zero 2 W runs an ONNX RL walk policy against Feetech STS3215 servos (over USB serial) and a BNO055 IMU (over I2C). This fork adds a Nix flake that packages the runtime, runs the walk as a NixOS service, builds per-robot SD images and deploys to running robots with colmena. `README.md` covers the original Raspbian/pip setup; `NIX.md` covers the Nix side in depth.

Most of the code only runs on the robot. Off the robot you can lint, type-check, byte-compile and build, but almost nothing can be exercised: importing `raw_imu` needs `board`/`busio` (Blinka), and `HWI` opens the serial port in its constructor.

## Commands

```bash
nix develop                     # python 3.12 + runtime, pypot, matplotlib, pytest, colmena
nix flake check                 # runtime builds/imports, every .py byte-compiles, pytest on ./tests (none yet)
ruff check .                    # config in pyproject.toml (line length 100, py312)
mypy .                          # check_untyped_defs; hardware libs have no stubs (ignore_missing_imports)

nix run .#v2-rl-walk -- --onnx_model_path ./model.onnx   # any packaged script: nix run .#<name>
nix build .#packages.aarch64-linux.sd-image-canard       # needs aarch64 or binfmt emulation
nix run .#deploy -- apply --on canard                    # colmena; builds locally, pushes over SSH to canard.local
```

A single test: `python -m pytest tests/test_x.py::test_name` (inside `nix develop`). `scripts/*_test.py` are hardware bring-up scripts, not pytest tests.

On a duck: `journalctl -u open-duck-walk -f`. Telemetry recordings land in `/var/lib/open-duck/telemetry`; summarize one with `python -m mini_bdx_runtime.telemetry <base>.bin`.

## Architecture

**The walk loop** (`scripts/v2_rl_walk_mujoco.py`, `RLWalk.run`) is the heart of the project. At `control_freq` (50 Hz) it builds an observation (`OBS_LAYOUT`: gyro, accelerometer, 7 gamepad commands, joint positions minus `init_pos`, scaled velocities, the last three actions, motor targets, foot contacts, the imitation phase as cos/sin), runs the policy, then `target = init_pos + action * action_scale`, optionally low-pass filtered, clipped to `max_target_offset` around the standing pose and rate-limited by `max_motor_velocity`. Head targets get the stick commands added on top. The observation layout and order must match what the policy was trained on (in Open_Duck_Playground): changing `OBS_LAYOUT`, `NUM_DOFS`, the joint order or the scales breaks every existing `.onnx`.

**Failure handling is deliberate.** Any NaN in the obs or the action skips the step (a NaN target sends a servo to an extreme position). If the servos have not answered for `SERVO_LOSS_S`, the walk calls `sys.exit(1)` so systemd (`Restart=always`) reopens the port: a USB drop-out on low battery is common. A disconnected controller pauses the walk. Per-second `STATS` lines are the main post-mortem trace, since a crash usually means a power cut.

**Hardware layer** (`mini_bdx_runtime/mini_bdx_runtime/`):
- `rustypot_position_hwi.py` `HWI`: joint name → servo ID mapping (dict order is the joint order everywhere, including obs and telemetry), `init_pos` standing pose, per-joint offsets from `duck_config.json` (added on write, subtracted on read). `turn_on()` ramps position and Kp over 2 s; sending everything at once browned the robot out.
- `raw_imu.py` `Imu`: a background thread doing one 18-byte I2C burst read per sample, rejecting spikes, recovering a reset sensor, rotating readings into the robot frame (x forward, y left, z up) with the configured orientation. The BNO055 runs in its own axes (remap set to identity); `imu.py` is the older driver-property-based implementation.
- `imu_orientation.py`: `imu_orientation` in `duck_config.json` as exactly one of `rotation_matrix`, `euler_deg` (intrinsic Z-Y'-X'') or `quaternion`; legacy `imu_upside_down` is still honored when the key is absent.
- `duck_config.py` `DuckConfig`: reads `duck_config.json` (default `~/duck_config.json`). Missing file → interactive prompt, which would hang a service.
- `telemetry.py`: append-only `.bin` records plus a `.json` sidecar holding the numpy dtype and metadata; written and fsynced from a background thread so the control loop never blocks on the SD card.
- Expression features (eyes, projector, antennas, speaker) are optional and only constructed when enabled in `duck_config.json`.

Scripts resolve their data files (`polynomial_coefficients.pkl`, `../mini_bdx_runtime/assets/`) relative to their own file, which is what lets the Nix wrappers run from any directory.

**Nix layout:**
- `flake.nix`: an overlay (`duckPython` with the runtime and its deps, `duckEnv`/`duckEnvHeadless`, the scripts package, the repackaged Pi kernel), packages/apps/checks, and one robot per directory under `ducks/`.
- `nix/python-packages.nix`: rustypot and onnxruntime come from upstream wheels (only `x86_64-linux` and `aarch64-linux`). `setup.cfg`'s pins are relaxed and its pypot/openai lines are stripped, so **a new runtime dependency must also be added to `propagatedBuildInputs` here**.
- `nix/scripts.nix`: the explicit list of scripts exposed as `open-duck-<name>` (underscores → dashes; `v2_rl_walk_mujoco` → `v2-rl-walk`). A new script must be added there to be packaged. `cam_test`, `fc_test` and `imu_client` are left out on purpose.
- `nix/module.nix`: `services.open-duck.walk` (turns options into the walk's CLI flags; `duckConfig` attrset or `duckConfigPath`), controller pairing, the `/dev/servohat` udev symlink, telemetry dir. Its options mirror `RLWalk`'s CLI args; keep both in sync when adding a flag.
- `nix/rpi-image.nix`: the shared Pi Zero 2 W image. It uses Raspberry Pi's downstream kernel repackaged from the Raspberry Pi OS `.deb` (`nix/rpi-kernel.nix`, with `nix/rpi-kernel.config` checked against it at build time) plus the firmware's device tree, because Blinka/RPi.GPIO need the Pi userspace ABI. The IMU runs on bit-banged `i2c-gpio` because the Pi's I2C controller mishandles the BNO055's clock stretching. See `NIX.md` for the rest of the reasoning before touching the kernel, firmware or boot settings.
- `ducks/<name>/`: what is specific to one robot (hostname, `duck.user`, Wi-Fi SSIDs, controller address, pinned machine-id, SSH keys, its `duck_config.json` with joint offsets and IMU calibration, optionally its own policy `.onnx`). Each one is both `nixosConfigurations.<name>` and a colmena node built from the same module list, so the image and a deploy produce the same store path. Wi-Fi passphrases are never in the repo: they go in `wireless.env` on the SD card's firmware partition.

## Conventions

Commit subjects are prefixed with the area they touch, lowercase, and say what changed for the robot (`walk: ...`, `nix: ...`, `canard: ...`, `raw_imu: ...`, `telemetry: ...`). Comments explain *why*, often citing measurements or the failure that motivated the code (brown-outs, I2C spikes, USB drop-outs); keep that style, and name tunables as module-level constants with a comment rather than inline numbers.
