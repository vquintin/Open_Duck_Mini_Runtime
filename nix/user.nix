# The duck's login user, mirroring the `canard` user from the Raspbian duck:
# same hardware groups, and by default the same name. Each duck may rename it
# and sets its SSH keys in ducks/<name>/default.nix:
#
#     duck.user = "bdxv2";
#     users.users.bdxv2.openssh.authorizedKeys.keys = [ ... ];
{ lib, config, ... }:
{
  options.duck.user = lib.mkOption {
    type = lib.types.str;
    default = "canard";
    description = ''
      Name of the duck's login user (initial password: the same). It is in
      wheel with passwordless sudo, and is the user colmena deploys as.
    '';
  };

  options.duck.deployHost = lib.mkOption {
    type = lib.types.str;
    default = "${config.networking.hostName}.local";
    defaultText = lib.literalExpression ''"''${config.networking.hostName}.local"'';
    example = "canard.tail43e490.ts.net";
    description = ''
      Address colmena deploys to over SSH: mDNS by default, or the duck's
      Tailscale name once it has joined the tailnet.
    '';
  };

  config.users.users.${config.duck.user} = {
    isNormalUser = true;
    extraGroups = [ "wheel" "dialout" "i2c" "gpio" "audio" "video" "input" "netdev" "plugdev" ];
    initialPassword = lib.mkDefault config.duck.user;
  };
}
