# Running Open Duck Mini with Nix / NixOS

This repository ships a Nix flake that packages the runtime, exposes each
script as an executable, provides a NixOS service (notably the RL walk), and can
build a bootable Raspberry Pi Zero 2 W SD-card image.

> Requires Nix with flakes enabled
> (`experimental-features = nix-command flakes`). The compiled `rustypot`
> dependency is consumed as an upstream wheel, so only `x86_64-linux` and
> `aarch64-linux` are supported.

## Run a script as a package

Every runnable script under `scripts/` is exposed as `open-duck-<name>`
(underscores become dashes):

```bash
nix run .#v2-rl-walk -- --onnx_model_path ./BEST_WALK_ONNX_2.onnx
nix run .#check-motors
nix run .#imu-server
nix run .#find-soft-offsets
```

Or build the whole bundle and put it on your PATH:

```bash
nix build .#scripts
./result/bin/open-duck-v2-rl-walk --help
```

Available commands: `open-duck-v2-rl-walk`, `-check-motors`, `-check-voltage`,
`-configure-motor`, `-configure-all-motors`, `-find-soft-offsets`, `-turn-on`,
`-turn-off`, `-head-puppet`, `-imu-server`, `-calibrate-imu`,
`-antennas-controller-test`, `-plot-recorded-data`, `-record-data`,
`-new-record-data`.

The wrappers `chdir` into the bundled `scripts/` directory so the relative
data files (`polynomial_coefficients.pkl`, the sound assets) resolve.

`cam_test`, `fc_test` and `imu_client` are intentionally not packaged (they need
`picamzero` / `FramesViewer`, which are Raspberry-Pi-camera or host-only).

## Run the walk (and other scripts) as a NixOS service

Add the module to your NixOS configuration:

```nix
{
  inputs.open-duck.url = "github:apirrone/Open_Duck_Mini_Runtime/nix-flake";

  # in your system modules:
  imports = [ open-duck.nixosModules.default ];

  services.open-duck.walk = {
    enable = true;
    restart = true;                       # start on boot
    onnxModelPath = "/var/lib/open-duck/BEST_WALK_ONNX_2.onnx";
    # Stable /dev/servohat symlink for the Waveshare servo board (see below).
    servoBoard = { vendorId = "1a86"; productId = "55d3"; };
    controlFreq = 50;
    actionScale = 0.25;
    pid = { p = 30; i = 0; d = 0; };
    pitchBias = 0.0;
    cutoffFrequency = 40.0;               # null to disable the action filter
    commands = true;                      # gamepad / keyboard control

    # Declarative duck_config.json (or set duckConfigPath to an existing file):
    duckConfig = {
      start_paused = true;
      imu_orientation.euler_deg = { roll = 0; pitch = 0; yaw = -90; };  # IMU in the robot frame
      phase_frequency_factor_offset = 0.0;
      expression_features = { eyes = false; projector = false; antennas = false; speaker = false; };
      joints_offsets = { left_hip_yaw = 0.0; /* ... */ };
    };
  };
}
```

The service runs as the `open-duck` system user, added to the
`dialout i2c gpio audio input` groups for hardware access, with its state in
`/var/lib/open-duck`. Secrets (e.g. `OPENAI_API_KEY`) go through
`services.open-duck.walk.environmentFile`.

With `servoBoard` set, udev names the board `/dev/servohat` whatever `ttyACM`
number it gets. When the servos stop answering (a USB drop-out, say), the walk
exits after half a second and systemd restarts it until the board is back.
The walk also pauses whenever the gamepad disconnects. Unpause with A (Cross on
a PS4 controller).

To pair a gamepad automatically, set its Bluetooth address:

```nix
services.open-duck.controller.address = "1C:96:5A:2F:7F:14";
```

The first time, put the controller in pairing mode (PS4: hold Share + PS until
the light bar flashes); afterwards pressing PS/Xbox reconnects it.

Manage it like any unit:

```bash
systemctl start open-duck-walk
journalctl -u open-duck-walk -f
```

## Build the Raspberry Pi Zero 2 W image

Each robot has a directory under `ducks/`; `ducks/<name>/default.nix` holds what
is specific to it (hostname, Wi-Fi networks, controller, servo board,
`duck_config.json` with
its IMU calibration and joint offsets) and is layered on the shared image in
`nix/rpi-image.nix`. Each one becomes `nixosConfigurations.<name>` and
`packages.aarch64-linux.sd-image-<name>`; `canard` is the first (`rpi` and
`sd-image` are aliases for it). To add a duck, copy `ducks/canard`, change the
hostname (and `duck.user` if it isn't `canard`), controller address and machine-id, and refill `duck_config.json` from
`find_soft_offsets` and `calibrate_imu`.

The image is an aarch64 NixOS system with the walk service, I2C, Bluetooth
(for the controller), SSH and the FTDI latency udev rule preconfigured. It:

- is reachable as `<hostname>.local` (avahi);
- joins the Wi-Fi networks listed in its `duck.wifiNetworks` (canard:
  `Okartie`, then `escargot`; bdxv2: `Okartie`, `kazoboner`, `O-P1-K-nooby`);
- starts the walk on boot, paused, with an upstream walk policy baked in
  (`BEST_WALK_ONNX_2.onnx` by default, `BEST_WALK_ONNX.onnx` on canard);
- pairs the duck's controller and uses `/dev/servohat` for the servo board.

### The kernel is Raspberry Pi's, not mainline

`boot.kernelPackages = pkgs.linuxPackages_rpi-deb`, and
`generic-extlinux-compatible.useGenerationDeviceTree = false` so U-Boot boots
the device tree the Pi firmware hands it rather than one out of the kernel's
`FDTDIR`.

Both are needed because the walk reaches the IMU and the antennas through
Adafruit Blinka, which goes through `RPi.GPIO`, which wants the Raspberry Pi
userspace ABI: `/dev/gpiomem`, the `Hardware`/`Revision` lines in
`/proc/cpuinfo`, and `linux,revision` in the device tree. Mainline provides
none of it on aarch64, and `import board` dies with *"This module can only be
run on a Raspberry Pi!"* — `BLINKA_FORCEBOARD` gets you past board detection
and no further. Keeping the firmware's device tree is also what makes
`config.txt`'s `dtparam`/`dtoverlay` lines take effect at all.

The downstream kernel is in no binary cache, and compiling it means hours under
emulation on an x86_64 builder, so it is instead repackaged from Raspberry Pi
OS's own `.deb` (`nix/rpi-kernel.nix`, pinned by hash to
`archive.raspberrypi.com`): the same 6.12.75-1+rpt1 as nixpkgs' `linux-rpi`,
with Raspberry Pi's config, which is what Raspbian ducks run. It can't be
patched or reconfigured, and NixOS assumes its own kernel config in places,
so `nix/rpi-image.nix` also:

- installs firmware uncompressed (`hardware.firmwareCompression = "none"`):
  the kernel has no `FW_LOADER_COMPRESS`, and `.zst` firmware means no Wi-Fi
  or Bluetooth;
- keeps the initrd to what it needs (the SD controller and ext4 are built in),
  without all-hardware's PC storage drivers or the TPM drivers, which this
  kernel doesn't have;
- gives `/dev/gpiomem` to the `gpio` group, as Raspbian does, or RPi.GPIO
  fails for the walk's user with *"No access to /dev/mem"*;
- runs the IMU's I2C bus as the bit-banged `i2c-gpio` on the I2C1 pins
  (bus 1) instead of the Pi's controller, which mishandles the BNO055's clock
  stretching: `config.txt` gets the `dtoverlay=i2c-gpio,...` line and the
  firmware partition the overlay (in the image, and on a flashed duck at
  activation, which then needs one more reboot to apply it).

`nix/rpi-kernel.config` is the `=y`/`=m` part of the `.deb`'s config, which
NixOS reads at evaluation time; the build fails if it drifts from the `.deb`.
To move to a newer kernel, bump `version` and the hash, and regenerate it from
the new `.deb`'s `/boot/config-*`.

The Wi-Fi passwords are not in the image: after flashing, create
`wireless.env` on the FAT firmware partition with one `psk_<ssid>=...` line per
network in `duck.wifiNetworks`, the SSID lowercased and anything but letters and
digits turned into `_` (canard: `psk_okartie=...` and
`psk_escargot=...`). Use Unix newlines — the value is taken verbatim, so a
CRLF file puts a stray `\r` in the passphrase and association fails with no
obvious error. The value may be the plain passphrase (8–63 characters) or a
64-hex PSK.

Note that the image overrides the mount options nixpkgs gives the firmware
partition: `sd-image.nix` mounts it `noauto` on the grounds that nothing needs
it at runtime, which would leave `/boot/firmware` empty and `wireless.env`
invisible to wpa_supplicant.

```bash
# On aarch64, or an x86_64 host with binfmt/qemu emulation
# (boot.binfmt.emulatedSystems = [ "aarch64-linux" ];):
nix build .#packages.aarch64-linux.sd-image-canard
```

Flash `result/sd-image/*.img` to an SD card and boot. The login user is the
duck's `duck.user`, `canard` by default (password: its name — change it;
bdxv2: `bdxv2`, password `bdx`). `ssh canard@canard.local`, then
`journalctl -u open-duck-walk -f` to watch the walk.

## Deploy to a running duck

Reflashing is only for a duck that doesn't boot. Once one is on the network,
push changes to it with [colmena](https://colmena.cli.rs):

```bash
nix develop -c colmena apply --on canard   # or: nix run .#deploy -- apply --on canard
nix run .#deploy -- apply-local            # (on the duck itself)
```

Every directory under `ducks/` is both a `nixosConfigurations.<name>` (for
building an image) and a colmena hive node (for deploying), from the same
module list — so the two cannot drift. They are in fact the same derivation:

```bash
nix eval --raw .#nixosConfigurations.canard.config.system.build.toplevel
nix eval --raw .#colmenaHive.nodes.canard.config.system.build.toplevel
# -> identical store paths
```

Nodes deploy over SSH to the duck's `duck.deployHost` (`<name>.local` unless
set; canard's is its Tailscale name, `canard.tail43e490.ts.net`) as the duck's `duck.user` (`canard` unless set), which is in
`wheel` with passwordless sudo on the image. Useful flags: `--on @duck` (all
ducks, by tag), `build` / `push` instead of `apply` to stage without
switching, and `--keep-result`.

Builds happen on the deploying host — a Pi Zero 2 W has 512 MB of RAM and no
business compiling anything — so an x86_64 builder needs aarch64 emulation:

```nix
boot.binfmt.emulatedSystems = [ "aarch64-linux" ];
```

## Tests / checks

```bash
nix flake check
```

runs:

- **runtime** — the `mini_bdx_runtime` package builds and imports.
- **scripts-compile** — every script byte-compiles (syntax check, no hardware).
- **pytest** — runs `pytest` at the repo root (passes cleanly when there are no
  tests yet; drop `tests/` in and they'll be picked up).

## Dev shell

```bash
nix develop      # python 3.12 with the runtime, pypot, matplotlib, pytest
```
