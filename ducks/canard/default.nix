# canard: the first Open Duck Mini, a Raspberry Pi Zero 2 W. Everything
# specific to this robot goes here; the shared Pi image is in nix/rpi-image.nix.
{ lib, pkgs, ... }:
{
  networking.hostName = "canard";
  # Deployed over Tailscale, wherever it is.
  duck.deployHost = "canard.tail43e490.ts.net";

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
    # On trial 2026-10-28: canard_walk_12 rocked standing still at 1.6-1.75
    # Hz (its balance loop too strong for the real body, the trunk lagging
    # the ankles ~110 ms more than in sim), calm at an action scale of 0.15
    # standing still (0.25 walking; the runtime's --standing_action_scale,
    # f8c0505, removed once canard_walk_13 stood still without it):
    # onnxModelPath = ./canard_walk_12.onnx;
    # c7, c6 trained on with the IMU 0-80 ms later, drawn per episode (as
    # canard's trunk lags), then its torque stage (Open_Duck_Playground
    # 322207a, S8 at 41.3M). In c4's sim, 3x the curriculum's episodes,
    # walk_12's then run31's in brackets: sharp stops with the IMU 60 ms
    # late, rocking 0% (75%, 82%), falls 2.9% (13%, 36%); sharp stops 2/729
    # falls, tipping back 2.5 deg median (3.3, 7.0); reversals 0/374 (0,
    # 13); standing jitter of those up 0.0031 (0.0033, 0.0056); real terrain
    # 37/540 (24, 33), all terrain 58/540 (50, 69), real-terrain speed 0.073
    # (0.073, 0.098); forward 0.118 (0.123, 0.125); leg torque rms 1.12 N.m
    # (1.14, 1.03). On trial at the full action scale standing still:
    # onnxModelPath = ./canard_walk_13.onnx;
    # Back to run31 (canard_walk_9, above) on 2026-10-29:
    # onnxModelPath = ./canard_walk_9.onnx;
    # c13, the curriculum from scratch without stand_still, the IMU 20-40 ms
    # late from S4, then pushed every 3-6 s (Open_Duck_Playground 5f35a89, S7
    # at 26.4M; its torque stage S8 never passed, each gain in torque or
    # jitter lost the terrain or the reversals). In sim, run31's in brackets:
    # pushed standing, catch steps 29% (15%), of those that fell 22% (6%),
    # median push held 0.64 m/s (0.57), walking 0.68 (0.54); sharp stops
    # with the IMU 20 ms late, falls 0% (1.8%), rocking 0% (8.1%); reversals
    # 2/125 (6/119); real terrain 15/180 (10), all terrain 22/180 (22),
    # real-terrain speed 0.067 (0.098); standing jitter 0.009 (0.0054);
    # forward 0.118 (0.127), sideways asymmetry 2.7% (7.0%), turning 1.6%
    # (9.7%); leg torque rms 1.15 N.m (1.03): watch the servos' heat.
    # On trial 2026-11-03: walks well but never settles standing still (gyro
    # 0.13 rad/s median, run31 0.008; hip yaw and ankles moving at 1-2 Hz):
    # onnxModelPath = ./canard_walk_14.onnx;
    # c13's S8 (torques -2.5e-2) at 27.5M of its extension, from walk_14's
    # stage: standing jitter 0.0074, leg torque rms 1.12 N.m, but reversals
    # 39/124 falls, real terrain 16/180, all terrain 29/180. To see what the
    # torque stage does standing still (no sharp reversals with it). On trial
    # 2026-11-04: softer than walk_14, less steady reversing:
    # onnxModelPath = ./canard_walk_15.onnx;
    # walk_15 trained on at S8 with a quarter of the command changes reversals
    # (Open_Duck_Playground ec46f64, 52.8M; it passes S8's 3c3c760 gate). In
    # sim, run31's in brackets: reversals 0/123 falls (6/119); leg torque rms
    # 1.08 N.m (1.03); standing jitter 0.0072 (0.0054); real terrain 14/180
    # (10) at 0.084 (0.098), all terrain 27/180 (22); pushed standing, catch
    # steps 28% (15%), median push held 0.67 m/s (0.57), walking 0.68 (0.54);
    # sharp stops with the IMU 20 ms late, no falls or rocking; turning
    # asymmetry 0.4% (9.7%). On trial since 2026-11-05, the one to go back to
    # (headRange 0):
    # onnxModelPath = ./canard_walk_16.onnx;
    # walk_16 trained on with head commands over half their range
    # (Open_Duck_Playground fe40de7, S9 at 26.4M, not yet past its gate). In
    # sim, walk_16's in brackets: head at half range, falls 2.4% (76%), error
    # 0.112 rad (0.136); head centred, standing jitter 0.035 (0.007), real
    # terrain 20/180 (17), all terrain 62/180 (26). To feel the head on the
    # right stick, on trial 2026-11-09:
    # onnxModelPath = ./canard_walk_17.onnx;
    # walk_17 trained on at S9 for 105M more (Open_Duck_Playground a66994e,
    # head tracking sigma 0.03; cur_head5's S9 at 52.8M, 131M of S9 in all).
    # In sim, walk_17's in brackets: head at half range, error 0.077 rad
    # (0.112), falls 10.4% (2.4%), walking at half commands 0.066 m/s; head
    # centred, standing jitter 0.026 (0.035), real terrain 11/180 (20), all
    # terrain 21/180 (62), reversals 0/125 falls, sidesteps 0.066 / 0.063
    # m/s. Full head range falls 38%: kept at half. On trial 2026-11-10:
    # onnxModelPath = ./canard_walk_18.onnx;
    # walk_18 trained on at S10, the head's full range, faster and sudden
    # (Open_Duck_Playground df54a57, cur_head6 at 60.3M, not yet past its
    # gate). In sim, walk_18's in brackets: full head range error 0.068 rad
    # (0.085), falls 8.0% (38%); half range 0.057 (0.077), falls 1.6% (10%);
    # standing jitter 0.014 (0.026); walking at half commands 0.025 m/s
    # (0.066), at full 0.105 (0.122); real terrain 14/180 (11), all 29/180
    # (21). Kept at half range until the head's bounds reach its joint stops
    # and head_puppet clears the combined stops. On trial 2026-11-10:
    # onnxModelPath = ./canard_walk_19.onnx;
    # S10's extension (cur_head6's S10_head_full_ext1 at 27.5M, restarted
    # from its S10 at 30.1M, 57.7M of S10 in all), taken before its
    # evaluation came. On trial 2026-11-10:
    onnxModelPath = ./canard_walk_20.onnx;
    headRange = 0.5;

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
