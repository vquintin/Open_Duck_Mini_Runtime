# Python package overrides for dependencies that are either not in nixpkgs
# (rustypot, the adafruit circuitpython libs, pypot) or that we build straight
# from this repository (mini-bdx-runtime).
#
# Consumed as a `packageOverrides` function via `python3.override` in the
# flake overlay, so `pyfinal`/`pyprev` are the usual python-package-set fixpoint
# arguments.
{ pkgs, src }:
pyfinal: pyprev:
let
  inherit (pkgs) lib fetchurl;
  system = pkgs.stdenv.hostPlatform.system;

  # Running the compiled extensions' import check means executing a target
  # binary. The aarch64 builds in this project only ever happen under qemu
  # emulation (building the Pi image on an x86_64 PC via binfmt), and that can't
  # be relied on: onnxruntime aborts at import because qemu-user doesn't emulate
  # the /sys cpuinfo probes it does. Note this is an emulated *native* build
  # (nixpkgs sees buildPlatform == hostPlatform == aarch64), so canExecute won't
  # catch it — gate on the target arch directly. Native x86_64 still gets the
  # import smoke-test; ELF deps are validated by autoPatchelf regardless.
  importsCheck = mods: lib.optionals (system == "x86_64-linux") mods;

  # rustypot ships a compiled (pyo3/maturin) extension. Building it from the
  # sdist would require vendoring the whole Cargo tree, so instead we consume
  # the upstream manylinux wheel and let autoPatchelf fix it up for Nix. Only
  # the two architectures we actually target are wired up.
  rustypotWheels = {
    "x86_64-linux" = {
      url = "https://files.pythonhosted.org/packages/b4/9d/4810ffd92b89fff48860af14bcc3d2239fe0211a4a8325168175dcd28105/rustypot-1.13.1-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl";
      hash = "sha256-mPhQL5avnhA0ieMYhOM0ihp7S1Z09jgzhvB21FqXPr4=";
    };
    "aarch64-linux" = {
      url = "https://files.pythonhosted.org/packages/e0/87/780735f89cd17a24f492fcbf5674ed0e1547934bc6f0b3576f16ffdd0d93/rustypot-1.13.1-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl";
      hash = "sha256-UDXKn2StAHZk9jgCbj1L1WUfZ3z23YgD6XEf+D+vZ7I=";
    };
  };

  # onnxruntime is consumed as an upstream wheel too: building it from source
  # takes ~15 min and isn't in the binary cache for recent revisions, and on the
  # Pi (aarch64) that would mean an emulated compile. 1.22.0 supports numpy 2.x,
  # matching nixpkgs.
  onnxruntimeWheels = {
    "x86_64-linux" = {
      url = "https://files.pythonhosted.org/packages/8c/60/16d219b8868cc8e8e51a68519873bdb9f5f24af080b62e917a13fff9989b/onnxruntime-1.22.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl";
      hash = "sha256-aWSpdXMa/BncNBj62NTgjEiSAUT/WQFJQppevg0V+zw=";
    };
    "aarch64-linux" = {
      url = "https://files.pythonhosted.org/packages/03/79/36f910cd9fc96b444b0e728bba14607016079786adf032dae61f7c63b4aa/onnxruntime-1.22.0-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl";
      hash = "sha256-yGARKOrvebY2FSrqdq5pgbfJ/IGmGPWEwV141CsxDxw=";
    };
  };

  # Helper for the pure-python adafruit wheels (py3-none-any, no patching).
  mkWheel = { pname, version, url, hash, deps ? [ ] }:
    pyfinal.buildPythonPackage {
      inherit pname version;
      format = "wheel";
      src = fetchurl { inherit url hash; };
      propagatedBuildInputs = deps;
      doCheck = false;
      # These adafruit wheels declare (partly circular) runtime deps on each
      # other; the closure is assembled at the env level, so skip the check.
      dontCheckRuntimeDeps = true;
    };
in
{
  rustypot = pyfinal.buildPythonPackage rec {
    pname = "rustypot";
    # 1.x: the Sts3215 controller reads temperature, voltage, load, current
    # and status, and its torque disable works (0.1.0's left the torque on).
    version = "1.13.1";
    format = "wheel";
    src = fetchurl (rustypotWheels.${system} or (throw
      "rustypot: no prebuilt wheel wired up for system ${system}"));
    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [ pkgs.stdenv.cc.cc.lib ];
    doCheck = false;
    pythonImportsCheck = importsCheck [ "rustypot" ];
  };

  onnxruntime = pyfinal.buildPythonPackage {
    pname = "onnxruntime";
    version = "1.22.0";
    format = "wheel";
    src = fetchurl (onnxruntimeWheels.${system} or (throw
      "onnxruntime: no prebuilt wheel wired up for system ${system}"));
    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [ pkgs.stdenv.cc.cc.lib ];
    propagatedBuildInputs = with pyfinal; [
      coloredlogs
      flatbuffers
      numpy
      packaging
      protobuf
      # Not sympy, which the wheel declares: only onnxruntime.tools'
      # symbolic shape inference imports it, never inference itself, and it
      # is ~100 MB of the duck's closure.
    ];
    doCheck = false;
    dontCheckRuntimeDeps = true;
    pythonImportsCheck = importsCheck [ "onnxruntime" ];
  };

  adafruit-platformdetect = pyprev.adafruit-platformdetect or (mkWheel {
    pname = "Adafruit-PlatformDetect";
    version = "3.84.1";
    url = "https://files.pythonhosted.org/packages/py3/A/Adafruit-PlatformDetect/Adafruit_PlatformDetect-3.84.1-py3-none-any.whl";
    hash = lib.fakeHash;
  });

  adafruit-blinka = mkWheel {
    pname = "Adafruit-Blinka";
    version = "9.1.0";
    url = "https://files.pythonhosted.org/packages/bb/97/17dac675981730d29b2d583de2aa0a9c2963d6c63f6bdc7eebf2711914ef/adafruit_blinka-9.1.0-py3-none-any.whl";
    hash = "sha256-b2F9Trt8LhTf4SWcY/Id9Kd9GxLV79ks9xrkvzTSG5E=";
    # setuptools is a *runtime* dep: board.py does `import pkg_resources` to
    # look up the adafruit_platformdetect version. Python 3.12 no longer ships
    # setuptools in the stdlib env, so without this every `import board` dies
    # with ModuleNotFoundError and takes the walk service down with it.
    deps = with pyfinal; [ adafruit-platformdetect adafruit-pureio pyftdi setuptools ];
  };

  adafruit-circuitpython-typing = mkWheel {
    pname = "adafruit-circuitpython-typing";
    version = "1.12.3";
    url = "https://files.pythonhosted.org/packages/cc/a1/578a03ba2bce0809b4e30974b47958963c9efe67b9fe74e7dbcdbbd45318/adafruit_circuitpython_typing-1.12.3-py3-none-any.whl";
    hash = "sha256-9tCgIVDh5O+1osKUW4jZSICf20ZYdfOZRxCLhGfJhtk=";
    deps = with pyfinal; [ typing-extensions ];
  };

  adafruit-circuitpython-busdevice = mkWheel {
    pname = "adafruit-circuitpython-busdevice";
    version = "5.2.17";
    url = "https://files.pythonhosted.org/packages/42/0d/66a4e0fbd7b35107f7dee04fed890f77b83d1da9dd1f7474af2ed21700ea/adafruit_circuitpython_busdevice-5.2.17-py3-none-any.whl";
    hash = "sha256-WoNPvguIsH0gSUvsVmgV2hVKpLG2aOLmZSd7NLNXjkQ=";
    deps = with pyfinal; [ adafruit-blinka adafruit-circuitpython-typing ];
  };

  adafruit-circuitpython-register = mkWheel {
    pname = "adafruit-circuitpython-register";
    version = "1.11.3";
    url = "https://files.pythonhosted.org/packages/90/12/e23f35b7b16d39295c0c63765b1be0342ae33991bb64974a86fcb29a7142/adafruit_circuitpython_register-1.11.3-py3-none-any.whl";
    hash = "sha256-g7XprRt6+zUzClSe9i+zzlz44TEo71L7brE/PNjyzKY=";
    deps = with pyfinal; [ adafruit-blinka adafruit-circuitpython-typing ];
  };

  adafruit-circuitpython-bno055 = mkWheel {
    pname = "adafruit-circuitpython-bno055";
    version = "5.4.22";
    url = "https://files.pythonhosted.org/packages/f0/d5/4d500c4f5b0ad8d643d9dd1b22e3b45b5e33beff4357b2473611d966f40e/adafruit_circuitpython_bno055-5.4.22-py3-none-any.whl";
    hash = "sha256-QkA3Hb/9UBt/aGOBm4XQUk7ct/g/PBe0F2q11Psr0v8=";
    deps = with pyfinal; [
      adafruit-blinka
      adafruit-circuitpython-busdevice
      adafruit-circuitpython-register
    ];
  };

  # pypot, from the pollen-robotics branch with feetech STS3215 support. Only a
  # handful of the motor-configuration / data-recording scripts use it, and they
  # only exercise the serial-bus IO, so we drop the heavier optional deps
  # (ikpy, opencv-contrib-python, wget) that are awkward to package.
  pypot = pyfinal.buildPythonPackage {
    pname = "pypot";
    version = "5.0.2-feetech";
    format = "setuptools";
    src = fetchurl {
      url = "https://github.com/pollen-robotics/pypot/archive/f6d305e70e1640f66188b256dfd1dcfeb8ab8a59.tar.gz";
      hash = "sha256-ApRE+6RaEIswc+9gAKuX+Loa2e6ZE7Pitq8nsvnXKPU=";
    };
    postPatch = ''
      substituteInPlace setup.py \
        --replace-quiet "'ikpy==3.0.1'," "" \
        --replace-quiet "'opencv-contrib-python'," "" \
        --replace-quiet "'wget'," ""
    '';
    propagatedBuildInputs = with pyfinal; [
      numpy
      scipy
      pyserial
      tornado
      bottle
      requests
    ];
    pythonRelaxDeps = true;
    doCheck = false;
    dontCheckRuntimeDeps = true;
    pythonImportsCheck = importsCheck [ "pypot" ];
  };

  # The runtime itself, built straight from this repo.
  mini-bdx-runtime = pyfinal.buildPythonPackage {
    pname = "mini-bdx-runtime";
    version = "0.0.1";
    pyproject = true;
    inherit src;

    build-system = [ pyfinal.setuptools ];

    # setup.cfg pins exact versions and pulls pypot from a git URL; drop the
    # git dependency (we inject our own pypot when needed) and let
    # pythonRelaxDeps take care of the version pins.
    # Drop the git pypot dependency (injected separately when needed) and the
    # openai pin (only used by the excluded LLM/camera scripts, and its build
    # is broken in the pinned nixpkgs).
    postPatch = ''
      substituteInPlace setup.cfg \
        --replace-quiet "    pypot @ git+https://github.com/pollen-robotics/pypot@support-feetech-sts3215" "" \
        --replace-quiet "    openai==1.70.0" ""
    '';

    propagatedBuildInputs = with pyfinal; [
      numpy
      scipy
      onnxruntime
      pygame
      rustypot
      adafruit-circuitpython-bno055
      adafruit-blinka
    ];

    pythonRelaxDeps = true;
    doCheck = false;
    dontCheckRuntimeDeps = true;
    pythonImportsCheck = importsCheck [ "mini_bdx_runtime" ];
  };
}
