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
    # Trained for canard (Open_Duck_Playground branch canard, 54231e4, run22
    # at 38M): its measured mass, the real soles, hills, pebbles and steps,
    # a left-right symmetric reference gait and symmetry augmentation. On
    # the home pose of init_pos (made its own mirror image), which it needs.
    # In sim: forward 0.12 for 0.15, turning ~1.0 for 1.0 both ways,
    # sideways 0.094 / 0.091 for 0.1 left / right. canard_walk_1.onnx, its
    # first policy (flat floors only), stepped sideways one way only.
    onnxModelPath = ./canard_walk_2.onnx;

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
