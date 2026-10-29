# NixOS module exposing the Open Duck Mini runtime as systemd services.
#
# The flagship service is `services.open-duck.walk`, which runs the RL walk
# policy (scripts/v2_rl_walk_mujoco.py). A small generic `services.open-duck.scripts`
# mechanism is also provided to run any other packaged script as a service.
{ self }:
{ config, lib, pkgs, ... }:
let
  cfg = config.services.open-duck;

  # The scripts package for the host's system, from this flake's overlay.
  defaultPackage = self.packages.${pkgs.stdenv.hostPlatform.system}.scripts;

  # The pinned upstream walk policies (nix/models.nix), from the overlay when
  # it is applied.
  models = pkgs.open-duck-models or (pkgs.callPackage ./models.nix { });

  # Turn an attrset into a duck_config.json in the nix store.
  configFile = name: value:
    pkgs.writeText "${name}.json" (builtins.toJSON value);

  walk = cfg.walk;

  # Resolve the duck config path: an explicit path wins, otherwise a generated
  # file from `duckConfig` (an assertion requires one of the two).
  walkConfigPath =
    if walk.duckConfigPath != null then walk.duckConfigPath
    else configFile "duck_config" walk.duckConfig;

  # Whether the walk may play sounds. Unknowable for a duckConfigPath file
  # (it may be edited on the device), so assume it might.
  speakerEnabled =
    walk.duckConfigPath != null
    || ((walk.duckConfig.expression_features or { }).speaker or false);

  walkArgs = lib.escapeShellArgs ([
    # Interpolated, not toString: a local file (./model.onnx) must be copied
    # to the store and into the duck's closure.
    "--onnx_model_path" "${walk.onnxModelPath}"
    "--duck_config_path" (toString walkConfigPath)
    "--serial_port" walk.serialPort
    "--control_freq" (toString walk.controlFreq)
    "-a" (toString walk.actionScale)
    "-p" (toString walk.pid.p)
    "-i" (toString walk.pid.i)
    "-d" (toString walk.pid.d)
    "--pitch_bias" (toString walk.pitchBias)
    "--imu_mode" walk.imu.mode
  ]
  ++ lib.optionals (walk.imu.mode == "amg") [ "--gyro_bandwidth" (toString walk.imu.gyroBandwidth) ]
  ++ lib.optionals (walk.cutoffFrequency != null) [ "--cutoff_frequency" (toString walk.cutoffFrequency) ]
  ++ lib.optionals (walk.telemetry.dir != null) [ "--telemetry_dir" walk.telemetry.dir ]
  ++ lib.optionals walk.commands [ "--commands" ]
  ++ walk.extraArgs);

  # video: /dev/vcio, the firmware mailbox the walk reads the Pi's undervoltage from
  hardwareGroups = [ "dialout" "i2c" "gpio" "audio" "input" "video" ];

  controller = cfg.controller;

  servoBoard = walk.servoBoard;
  hasServoBoard = servoBoard.vendorId != null;
  # systemd device unit of the stable symlink, e.g. dev-servohat.device.
  servoDeviceUnit = "dev-${servoBoard.name}.device";

  # Bond + trust the gamepad once; afterwards the controller reconnects to the
  # duck by itself whenever its PS/Xbox button is pressed.
  pairScript = pkgs.writeShellScript "open-duck-pair-controller" ''
    set -u
    addr=${lib.escapeShellArg controller.address}
    btctl() { ${pkgs.bluez}/bin/bluetoothctl "$@"; }

    btctl power on
    until btctl info "$addr" | grep -q "Bonded: yes"; do
      echo "Controller $addr not bonded yet: put it in pairing mode (hold Share + PS until the light bar flashes)."
      # Drop any stale, half-paired entry before retrying.
      btctl remove "$addr" >/dev/null 2>&1 || true
      btctl --timeout 10 scan on >/dev/null
      btctl --agent NoInputNoOutput --timeout 20 pair "$addr" || sleep 5
    done
    btctl trust "$addr"
    btctl connect "$addr" || true
    echo "Controller $addr bonded and trusted."
  '';
in
{
  options.services.open-duck = {
    package = lib.mkOption {
      type = lib.types.package;
      default = defaultPackage;
      defaultText = lib.literalExpression "open-duck flake scripts package";
      description = "The open-duck-scripts package providing the executables.";
    };

    controller = {
      address = lib.mkOption {
        type = lib.types.nullOr (lib.types.strMatching "([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}");
        default = null;
        example = "1C:96:5A:2F:7F:14";
        description = ''
          Bluetooth address of the gamepad (Xbox or PS4) driving the duck. When
          set, the duck bonds with it on boot (the controller must be in pairing
          mode the first time) and trusts it, so it reconnects automatically.
        '';
      };
    };

    walk = {
      enable = lib.mkEnableOption "the Open Duck Mini RL walk service";

      onnxModelPath = lib.mkOption {
        type = lib.types.path;
        default = models.best-walk-2;
        defaultText = lib.literalExpression "pkgs.open-duck-models.best-walk-2";
        example = lib.literalExpression "pkgs.open-duck-models.best-walk";
        description = ''
          Path to the ONNX walk policy checkpoint. Defaults to the pinned
          upstream BEST_WALK_ONNX_2.onnx fetched at build time.
        '';
      };

      duckConfigPath = lib.mkOption {
        type = lib.types.nullOr lib.types.path;
        default = null;
        description = ''
          Path to an existing duck_config.json, e.g. a string path such as
          "/var/lib/open-duck/duck_config.json" to use a file edited on the
          device. If null, {option}`duckConfig` must be set and is rendered to
          a config file.
        '';
      };

      duckConfig = lib.mkOption {
        type = lib.types.nullOr (lib.types.attrsOf lib.types.anything);
        default = null;
        example = lib.literalExpression ''
          {
            start_paused = false;
            imu_orientation.euler_deg = { roll = 0; pitch = 0; yaw = -90; };
            phase_frequency_factor_offset = 0.0;
            expression_features = { eyes = false; projector = false; antennas = false; speaker = false; };
            joints_offsets = { left_hip_yaw = 0.0; /* ... */ };
          }
        '';
        description = "Declarative duck configuration, rendered to JSON. Ignored if duckConfigPath is set.";
      };

      serialPort = lib.mkOption {
        type = lib.types.str;
        default = if hasServoBoard then "/dev/${servoBoard.name}" else "/dev/ttyACM0";
        defaultText = lib.literalExpression ''
          if servoBoard.vendorId != null then "/dev/''${servoBoard.name}" else "/dev/ttyACM0"
        '';
        description = "Serial port of the motor control board.";
      };

      servoBoard = {
        vendorId = lib.mkOption {
          type = lib.types.nullOr (lib.types.strMatching "[0-9a-f]{4}");
          default = null;
          example = "1a86";
          description = ''
            USB vendor id of the servo driver board. When set (with
            {option}`productId`), udev gives the board a stable
            /dev/''${name} symlink, so a USB drop-out that renumbers
            ttyACM0 to ttyACM1 doesn't break the walk: the walk exits
            when the servos stop answering and starts again (paused, if
            start_paused is set) once the board is back.
          '';
        };

        productId = lib.mkOption {
          type = lib.types.nullOr (lib.types.strMatching "[0-9a-f]{4}");
          default = null;
          example = "55d3";
          description = "USB product id of the servo driver board.";
        };

        name = lib.mkOption {
          type = lib.types.strMatching "[A-Za-z0-9_]+";
          default = "servohat";
          description = "Name of the stable /dev symlink for the servo driver board.";
        };
      };

      controlFreq = lib.mkOption {
        type = lib.types.int;
        default = 50;
        description = "Control loop frequency in Hz.";
      };

      actionScale = lib.mkOption {
        type = lib.types.numbers.nonnegative;
        default = 0.25;
        description = "Action scale applied to the policy output.";
      };

      pid = {
        p = lib.mkOption { type = lib.types.int; default = 30; description = "Proportional gain."; };
        i = lib.mkOption { type = lib.types.int; default = 0; description = "Integral gain."; };
        d = lib.mkOption { type = lib.types.int; default = 0; description = "Derivative gain."; };
      };

      pitchBias = lib.mkOption {
        type = lib.types.numbers.between (-90.0) 90.0;
        default = 0.0;
        description = "User pitch bias in degrees.";
      };

      cutoffFrequency = lib.mkOption {
        type = lib.types.nullOr lib.types.numbers.nonnegative;
        default = null;
        description = "Low-pass action filter cutoff frequency (Hz). Null disables filtering.";
      };

      nice = lib.mkOption {
        type = lib.types.nullOr (lib.types.ints.between (-20) 19);
        default = -5;
        description = ''
          The walk's nice value: a larger share of the CPU than other
          processes', the kernel's own work (USB serial, I2C, Wi-Fi) at nice 0
          or higher priority still served. Not SCHED_FIFO: at FIFO 20 canard's
          servo reads took up to 80 ms (p99, 7 ms before), the kernel's USB
          work behind the walk's threads (2026-10-28). At -5 canard's steps
          were regular (0.08% over 25 ms in 11 min). Null leaves it at 0.
        '';
      };

      telemetry = {
        dir = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = "/var/lib/open-duck/telemetry";
          description = ''
            Where the walk records every step it walks (observation, policy
            action, target sent, timing; RB / R1 on the gamepad marks a moment), one
            file per walk, about 1.6 MB a minute. Null disables recording.
            Read back with `python -m mini_bdx_runtime.telemetry`.
          '';
        };

        keepFor = lib.mkOption {
          type = lib.types.str;
          default = "30d";
          description = "How long recordings are kept (a systemd-tmpfiles age).";
        };
      };

      imu = {
        mode = lib.mkOption {
          type = lib.types.enum [ "ndof" "amg" ];
          default = "amg";
          description = ''
            The BNO055's operating mode. "amg" reads the gyro and the
            accelerometer raw, with the filters below: the policy's gyro is
            then ~30 ms fresher than in the fused "ndof" (which the walk never
            needed: it uses no orientation). With "ndof", run27 standing still
            swayed at 2 Hz (0.29 rad/s); with "amg" it stood still (2026-10-21).
          '';
        };

        gyroBandwidth = lib.mkOption {
          type = lib.types.enum [ 12 23 32 47 64 116 230 523 ];
          default = 116;
          description = "Gyro low-pass bandwidth in Hz, in \"amg\" mode (mini_bdx_runtime/imu_modes.py).";
        };
      };

      commands = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Enable external commands (gamepad / keyboard).";
      };

      extraArgs = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        description = "Extra command-line arguments passed to v2_rl_walk_mujoco.py.";
      };

      environmentFile = lib.mkOption {
        type = lib.types.nullOr lib.types.path;
        default = null;
        description = "systemd EnvironmentFile for secrets (e.g. OPENAI_API_KEY).";
      };

      user = lib.mkOption {
        type = lib.types.str;
        default = "open-duck";
        description = "User the walk service runs as.";
      };

      group = lib.mkOption {
        type = lib.types.str;
        default = "open-duck";
        description = "Group the walk service runs as.";
      };

      restart = lib.mkOption {
        type = lib.types.bool;
        default = false;
        description = ''
          Automatically (re)start the walk on boot. Off by default: an
          unattended walking robot on boot is usually not what you want.
        '';
      };
    };
  };

  config = lib.mkMerge [
  (lib.mkIf (controller.address != null) {
    hardware.bluetooth.enable = true;
    hardware.bluetooth.powerOnBoot = true;
    # Gamepads over Bluetooth HID.
    boot.kernelModules = [ "uhid" "hid_playstation" ];

    systemd.services.open-duck-controller = {
      description = "Pair and trust the Open Duck Mini gamepad";
      wantedBy = [ "multi-user.target" ];
      after = [ "bluetooth.service" ];
      requires = [ "bluetooth.service" ];
      serviceConfig = {
        # Not oneshot: waiting for the controller must not stall boot.
        Type = "exec";
        RemainAfterExit = true;
        ExecStart = pairScript;
      };
    };
  })

  (lib.mkIf walk.enable {
    assertions = [
      {
        assertion = (servoBoard.vendorId == null) == (servoBoard.productId == null);
        message = "services.open-duck.walk.servoBoard: set both vendorId and productId, or neither.";
      }
      {
        # Without a config the walk prompts on stdin, which crash-loops under systemd.
        assertion = walk.duckConfigPath != null || walk.duckConfig != null;
        message = ''
          services.open-duck.walk: set duckConfig, or duckConfigPath (e.g.
          "/var/lib/open-duck/duck_config.json" for a file edited on the device).
        '';
      }
    ];

    services.udev.extraRules = lib.mkMerge [
      (lib.mkIf hasServoBoard (''
        SUBSYSTEM=="tty", ATTRS{idVendor}=="${servoBoard.vendorId}", ATTRS{idProduct}=="${servoBoard.productId}", SYMLINK+="${servoBoard.name}", TAG+="systemd"''
        # (Re)start the walk whenever the board (re)appears.
        + lib.optionalString walk.restart '', ENV{SYSTEMD_WANTS}+="open-duck-walk.service"''
        + "\n"))
      # The firmware's throttled / undervoltage state (pi_power.py), root-only by default.
      ''
        KERNEL=="vcio", GROUP="video", MODE="0660"
      ''
    ];

    users.users.${walk.user} = lib.mkIf (walk.user == "open-duck") {
      isSystemUser = true;
      group = walk.group;
      extraGroups = hardwareGroups;
      home = "/var/lib/open-duck";
      createHome = true;
    };
    users.groups.${walk.group} = lib.mkIf (walk.group == "open-duck") { };

    # World-readable (nothing secret in it), so recordings can be fetched
    # over scp as any user; aged out.
    systemd.tmpfiles.rules = lib.mkIf (walk.telemetry.dir != null) [
      "d ${walk.telemetry.dir} 0755 ${walk.user} ${walk.group} ${walk.telemetry.keepFor}"
    ];

    systemd.services.open-duck-walk = {
      description = "Open Duck Mini RL walk";
      wantedBy = lib.mkIf walk.restart [ "multi-user.target" ];
      # Not after network.target: the walk needs no network, and waiting for
      # Wi-Fi held it back a second or two at every boot.
      after = [ "sound.target" ]
        ++ lib.optional (controller.address != null) "open-duck-controller.service"
        ++ lib.optional hasServoBoard servoDeviceUnit;
      # No BindsTo on the board: when it dropped out and came back within a
      # second, udev's start job hit the BindsTo stop job still running
      # ("Resource deadlock avoided"), systemd dropped the start, and the
      # servos stayed frozen on their last target. The walk exits by itself
      # when the servos go silent, and Restart= brings it back.
      # Keep retrying however many times the board or controller drops out.
      startLimitIntervalSec = 0;

      serviceConfig = {
        ExecStart = "${cfg.package}/bin/open-duck-v2-rl-walk ${walkArgs}";
        User = walk.user;
        Group = walk.group;
        SupplementaryGroups = hardwareGroups;
        StateDirectory = "open-duck";
        WorkingDirectory = "/var/lib/open-duck";
        Restart = "always";
        RestartSec = 1;
        EnvironmentFile = lib.mkIf (walk.environmentFile != null) walk.environmentFile;
        # HOME so that scripts falling back to ~/duck_config.json behave.
        Environment = [
          "HOME=/var/lib/open-duck"
          # Use the evdev joystick backend: the layouts in xbox_controller.py
          # assume its axis/button numbering (and hidraw is root-only anyway).
          "SDL_JOYSTICK_HIDAPI=0"
          # Headless: pygame's event queue still needs a video driver.
          "SDL_VIDEODRIVER=dummy"
          # stdout isn't a tty under systemd, so Python block-buffers it and
          # the walk's prints (UNPAUSE, "Policy control budget exceeded",
          # [IMU] errors) sit in memory — and are lost on a brown-out reset.
          "PYTHONUNBUFFERED=1"
        ]
        # pygame.init() opens the sound card even when nothing plays, and
        # ALSA then logs an "underrun occurred" every ~80 ms (~1500 journal
        # lines in 2 min on a Pi Zero 2 W). No speaker, no sound card.
        ++ lib.optional (!speakerEnabled) "SDL_AUDIODRIVER=dummy";
        Nice = lib.mkIf (walk.nice != null) walk.nice;
        # The walk only cleans up (peripherals, "TURNING OFF") on
        # KeyboardInterrupt. On SIGTERM it ignored the stop, and systemd
        # SIGKILLed it after the 90 s stop timeout.
        KillSignal = "SIGINT";
      };
    };
  })
  ];
}
