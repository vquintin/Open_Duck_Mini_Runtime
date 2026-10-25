# bdxv2: a second Open Duck Mini, a Raspberry Pi Zero 2 W, with its IMU mounted
# upside down. Everything specific to this robot goes here; the shared Pi image
# is in nix/rpi-image.nix.
{ lib, ... }:
{
  networking.hostName = "bdxv2";
  duck.user = "bdxv2";

  # Wi-Fi networks, most preferred first; each one's passphrase goes in
  # wireless.env on the firmware partition, as psk_<ssid> (see nix/wifi.nix).
  duck.wifiNetworks = [ "Okartie" "kasoboner" "O-P1-K-nooby" ];
  # Pinned so that /etc being an overlay doesn't hand the duck a new one (and
  # its journal a new directory) on every boot.
  environment.etc.machine-id.text = "1798b7897f922e6449fc281238e977e0\n";

  # The PS5 DualSense; bonded on first boot (hold Create + PS), then reconnects
  # on its own.
  services.open-duck.controller.address = "AC:36:1B:87:2A:2D";

  # Password logins over SSH, as well as the keys (which colmena deploys with).
  users.users.bdxv2.initialPassword = "bdx";
  services.openssh.settings.PasswordAuthentication = true;
  users.users.bdxv2.openssh.authorizedKeys.keys = [
    # From nixos-config (modules/meta/keys.nix, my.sshKeys).
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC1pc8NFhXyHkzqasmVCpReT0ctaGB7oIyY2WGMDjtqsyc8KaOglPKGX8ibyx6hITB4/81qKffeJ8uNdNW549wlOTvOMnBptDXBrOC+JtNWfz94jwWipWT3AEaeLKsMuNJKxPm+VN0wyg8Mv6J4stWcrPTVAyv8FrM4siV3yyVF6i1PsANhnSa/z++uZNieDCoGl/Nit5m8JI45vaQ/ZHNZ8Hr88Sl5C/RMdp545bTedunlAnCDcMivrjfz9flwQ1OU57fI5n0hq6y+zcUHCbYsU+9/ZXIZon6dgM5b9nUX6kxQwse0ZJv1IvxGae/8zFxOhKVUfUyZtSZ7WNDXrjIEvF9HehYuu+wQ9E7EdFN6BPewUsWLHzp0f6FWuLERq3S28B0hkyFGSu8tdjHH0dZH8pluzfepZbSl5L4FKQCV9VEnViLEKSd+mKuvAbBuoyoJPL3GZ0CFTOVpp3yS1/p7+Qe2H8wtJv3zCghpC1pddG+LJfnujltNczJmk5lIrfk= virgile@laptop-vquintin"
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDGgsoGWvO4ZtWyjJMpJ+beie8/+JTFFWDAQyXxztbOO virgile@desktop"
    # From the Raspbian duck's ~/.ssh/authorized_keys.
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDPcPy0g5Z7SdJZxDg/K2YdMHhFWyy8xHNAWChxs8AyIvirouhI8G2GSNF9+ZcCcJ+LxEsTEWK8eiP0dafUCDVKDIUWLSQuZnmNCC9KRrAZEqY59qPz6iINbW7WrNnqs9pbfip9D/OEflA5Uq70vKuPaC7xNdwxF2kk8/+NCRxjGgA/ravUma7L6bxCuguMS4XcJb3Cg4y2+XmQPQ1Si3MDK6aHpPoU7pKscLzGCLUcpev0q3syW2eyAOQ9BhkJJFod99K0aUSsRfQgMS6PY2QOce0XlpaqeURvDHR+5C4muTo628IeAC7xULutCDlfqU+aa96ZMjXDQQtpOBJZdaZ7iYNvYRce6ONkB4ilx6Ug9M6/InqBSCRDT43fv5BtEJYzqzc6m1kau/GFk3hQoxGOzbY3xSkTn5zFN9BGoQY9odFXY4wZN/12+yCiRScro1e2oAjYr2RRhh/J/nnZv2SdMcn+Qc7uY2A9VklS2yV8cQDy5ufmnujmjsCd+NW7HGE= vquintin@desktop"
    # Olivier's Mac (~/.ssh/idssh).
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIABMIKdgyqVwBimAQPlecj3t1wUq9CEQGhwxS09B4KS/ payetolivier@Mac.home"
  ];

  services.open-duck.walk = {
    # Waveshare bus servo adapter (CH343), reachable as /dev/servohat whatever
    # ttyACM number it gets after a low-battery USB drop-out.
    servoBoard = {
      vendorId = "1a86";
      productId = "55d3";
    };

    # The IMU is upside down and turned the other way round from the Open Duck
    # Mini v2's imu_upside_down mounting: roll 180, yaw +90, checked by tilting
    # the duck nose down and left side down. Its accelerometer offsets (LSB,
    # 0.01 m/s^2) come from a sphere fit over six resting poses, measured
    # raw: a constant -1.7 m/s^2 on the sensor's y axis, which alone made the
    # standing duck read 7 degrees nose down. The sensor also reads 1.8% low on
    # every axis, which offsets can't correct (|a| = 9.63 at rest). Joint
    # offsets are not calibrated yet (find_soft_offsets).
    # The image starts the walk on boot, so it starts paused (press A / Cross
    # to start walking). onnxModelPath is the module's default, upstream
    # BEST_WALK_ONNX_2.
    duckConfig = lib.importJSON ./duck_config.json // { start_paused = true; };
  };
}
