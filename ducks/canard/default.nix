# canard: the first Open Duck Mini, a Raspberry Pi Zero 2 W. Everything
# specific to this robot goes here; the shared Pi image is in nix/rpi-image.nix.
{ lib, pkgs, ... }:
{
  networking.hostName = "canard";

  # Wi-Fi networks, most preferred first; each one's passphrase goes in
  # wireless.env on the firmware partition, as psk_<ssid> (see nix/wifi.nix).
  duck.wifiNetworks = [ "Okartie" "escargot" ];
  # The one systemd generated on first boot, pinned so that /etc being an
  # overlay doesn't hand the duck a new one (and its journal a new directory).
  environment.etc.machine-id.text = "ad6b9aecce82442b998d1cc6f434a0e2\n";

  # The PS4 DualShock 4; bonded on first boot, then reconnects on its own.
  services.open-duck.controller.address = "1C:96:5A:2F:7F:14";

  users.users.canard.openssh.authorizedKeys.keys = [
    # From nixos-config (modules/meta/keys.nix, my.sshKeys).
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC1pc8NFhXyHkzqasmVCpReT0ctaGB7oIyY2WGMDjtqsyc8KaOglPKGX8ibyx6hITB4/81qKffeJ8uNdNW549wlOTvOMnBptDXBrOC+JtNWfz94jwWipWT3AEaeLKsMuNJKxPm+VN0wyg8Mv6J4stWcrPTVAyv8FrM4siV3yyVF6i1PsANhnSa/z++uZNieDCoGl/Nit5m8JI45vaQ/ZHNZ8Hr88Sl5C/RMdp545bTedunlAnCDcMivrjfz9flwQ1OU57fI5n0hq6y+zcUHCbYsU+9/ZXIZon6dgM5b9nUX6kxQwse0ZJv1IvxGae/8zFxOhKVUfUyZtSZ7WNDXrjIEvF9HehYuu+wQ9E7EdFN6BPewUsWLHzp0f6FWuLERq3S28B0hkyFGSu8tdjHH0dZH8pluzfepZbSl5L4FKQCV9VEnViLEKSd+mKuvAbBuoyoJPL3GZ0CFTOVpp3yS1/p7+Qe2H8wtJv3zCghpC1pddG+LJfnujltNczJmk5lIrfk= virgile@laptop-vquintin"
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDGgsoGWvO4ZtWyjJMpJ+beie8/+JTFFWDAQyXxztbOO virgile@desktop"
    # From the Raspbian duck's ~/.ssh/authorized_keys.
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDPcPy0g5Z7SdJZxDg/K2YdMHhFWyy8xHNAWChxs8AyIvirouhI8G2GSNF9+ZcCcJ+LxEsTEWK8eiP0dafUCDVKDIUWLSQuZnmNCC9KRrAZEqY59qPz6iINbW7WrNnqs9pbfip9D/OEflA5Uq70vKuPaC7xNdwxF2kk8/+NCRxjGgA/ravUma7L6bxCuguMS4XcJb3Cg4y2+XmQPQ1Si3MDK6aHpPoU7pKscLzGCLUcpev0q3syW2eyAOQ9BhkJJFod99K0aUSsRfQgMS6PY2QOce0XlpaqeURvDHR+5C4muTo628IeAC7xULutCDlfqU+aa96ZMjXDQQtpOBJZdaZ7iYNvYRce6ONkB4ilx6Ug9M6/InqBSCRDT43fv5BtEJYzqzc6m1kau/GFk3hQoxGOzbY3xSkTn5zFN9BGoQY9odFXY4wZN/12+yCiRScro1e2oAjYr2RRhh/J/nnZv2SdMcn+Qc7uY2A9VklS2yV8cQDy5ufmnujmjsCd+NW7HGE= vquintin@desktop"
  ];

  services.open-duck.walk = {
    # Trained for canard (Open_Duck_Playground branch canard, de0ffa5, run30
    # at 41M, from run27 at 41M = canard_walk_7.onnx, which walked canard
    # steadily once its IMU read raw): the raw IMU 0-40 ms late, the actions
    # 0-40 ms, the servos' kp x0.85-1.15, the gyro's gain drawn per episode,
    # the soles fitted on canard's walk (25 N.m/rad, damped 0.13); symmetry
    # augmentation and mirror loss 0.3. In sim: falls on the real terrain
    # 7/180 (all terrain 14/180, run27 36), forward 0.089, sideways 0.094 /
    # 0.096, standing leg jitter 0.009 (0.035 with sensor noise).
    # onnxModelPath = ./canard_walk_8.onnx;  # run30, the fallback
    # run31 at 32M, on trial since 2026-10-22:
    # run31 at 32M (dba709e, from run30), trained on commands changing every
    # 2-6 s, a quarter of them stops, as canard tipped back and fell on sharp
    # stops with run30. In sim: sharp stops from 0.15 m/s 0/25 falls (run30
    # 5/26), tipping back 5.5 deg (6.9); real terrain 10/180, all terrain
    # 22/180; standing jitter 0.011.
    # On trial again since 2026-10-25, with the runtime reading the IMU and the
    # servos at once (the loop ~19 ms faster): on c4's sim it passes every gate
    # (reversals 5%, sharp stops 0%, no rocking, terrain 10 / 22). The
    # fallback:
    # onnxModelPath = ./canard_walk_9.onnx;
    # run32 at 38M (66d8a44, from run30): commands every 3-8 s, 15% stops.
    # In sim: real terrain 6/180, all terrain 31/180; sharp stops 1/26,
    # tipping back 6.4 deg; standing jitter 0.010. To try against run31:
    # onnxModelPath = ./canard_walk_10.onnx;
    # c3, the curriculum from scratch (Open_Duck_Playground dccf088,
    # curriculum/canard.toml, S7 at 11.8M of its extension). In sim, run31's
    # in brackets: real terrain 8/180 (10), all terrain 17/180 (22); sharp
    # stops 0/269 (0/237), tipping back 1.0 deg median (5.5); reversals
    # 0/135 (7/118); standing jitter 0.010 (0.010), calm 95% (98%);
    # forward 0.122 (0.135), half 0.081 (0.073), sideways 0.081 / 0.083
    # (0.105 / 0.094). On trial since 2026-10-24:
    # onnxModelPath = ./canard_walk_11.onnx;  # rocked standing still after sharp stops
    # c6, the curriculum from scratch with stops, reversals and torque last
    # (Open_Duck_Playground 06d4f94, S7 at torques -2.5e-2, 35.4M; c6's
    # final.onnx). In c4's sim, 3x the curriculum's episodes, run31's in
    # brackets: real terrain 24/540 (33), all terrain 50/540 (69), real-terrain
    # speed 0.073 (0.098); sharp stops 0/729 (0/693), tipping back 3.3 deg
    # median (7.0), no rocking; reversals 0/374 (13/352); standing jitter
    # 0.014 (0.012), calm 81% (97%); forward 0.123 (0.125), turning 0.98 /
    # 0.99 (0.98 / 1.07); leg torque rms 1.14 N.m (1.03): watch the servos'
    # heat.
    onnxModelPath = ./canard_walk_12.onnx;
    # On trial 2026-10-28: canard_walk_12 rocked standing still at 1.6-1.75
    # Hz (its balance loop too strong for the real body, the trunk lagging
    # the ankles ~110 ms more than in sim); 0.25 walking.
    standingActionScale = 0.15;
    # A little ahead of the other processes; the kernel's work (USB serial,
    # I2C, Wi-Fi) at nice 0 or higher priority still served. Its steps were
    # already regular (0.08% over 25 ms in 11 min, 2026-10-28).
    nice = -5;

    # Waveshare bus servo adapter (CH343), reachable as /dev/servohat whatever
    # ttyACM number it gets after a low-battery USB drop-out.
    servoBoard = {
      vendorId = "1a86";
      productId = "55d3";
    };

    # duck_config.json is copied verbatim from the Raspbian duck's
    # ~/duck_config.json: calibrated IMU offsets and per-joint zero offsets.
    # The image starts the walk on boot, so it starts paused (press A / Cross to
    # start walking).
    duckConfig = lib.importJSON ./duck_config.json // { start_paused = true; };
  };
}
