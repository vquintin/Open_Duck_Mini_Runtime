# Packages the runnable scripts from ./scripts as individual executables.
#
# The scripts load a few files by *relative* path (notably
# "./polynomial_coefficients.pkl" and "../mini_bdx_runtime/assets/"), so we
# assemble a small runtime tree and make each wrapper chdir into it before
# exec'ing python.
{ pkgs, src, duckEnv }:
let
  inherit (pkgs) lib;

  # Scripts we expose. Excluded on purpose:
  #   cam_test / fc_test  -> need picamzero (Raspberry-Pi-camera only)
  #   imu_client          -> needs FramesViewer (not packaged)
  scripts = [
    "v2_rl_walk_mujoco"
    "check_motors"
    "check_voltage"
    "configure_motor"
    "configure_all_motors"
    "find_soft_offsets"
    "turn_on"
    "turn_off"
    "head_puppet"
    "imu_server"
    "calibrate_imu"
    "antennas_controller_test"
    "plot_recorded_data"
    "record_data"
    "new_record_data"
    "excite_servos"
    "sway_delay"
    "read_bench"
  ];

  # Nicer command names than the raw filename for a few scripts.
  nameOverrides = {
    v2_rl_walk_mujoco = "v2-rl-walk";
  };

  # A stable command name for each script, e.g. open-duck-v2-rl-walk.
  cmdName = s: "open-duck-" +
    (nameOverrides.${s} or (lib.replaceStrings [ "_" ] [ "-" ] s));
in
pkgs.stdenv.mkDerivation {
  pname = "open-duck-scripts";
  version = "0.0.1";
  inherit src;

  nativeBuildInputs = [ pkgs.makeWrapper ];

  # Nothing to compile; just lay out the runtime tree and the wrappers.
  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall

    share=$out/share/open-duck
    mkdir -p "$share/scripts" "$share/mini_bdx_runtime"

    cp -r scripts/. "$share/scripts/"
    # assets the scripts resolve relative to their own file (../mini_bdx_runtime/assets/)
    if [ -d mini_bdx_runtime/assets ]; then
      cp -r mini_bdx_runtime/assets "$share/mini_bdx_runtime/assets"
    fi

    mkdir -p $out/bin
    ${lib.concatMapStringsSep "\n" (s: ''
      makeWrapper ${duckEnv}/bin/python $out/bin/${cmdName s} \
        --add-flags "$share/scripts/${s}.py"
    '') scripts}

    runHook postInstall
  '';

  meta = {
    description = "Open Duck Mini runtime scripts as individual executables";
    mainProgram = cmdName "v2_rl_walk_mujoco";
  };
}
