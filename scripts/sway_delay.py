"""Sway a standing duck back and forth with its ankles (or its neck: --joints), no policy, and record
when the encoders and the IMU see it: the loop's delays without the policy
closing the loop.

The duck stands on its feet, the walk stopped (it owns the servo bus and the
IMU): sudo systemctl stop open-duck-walk. Both ankles move together around
init_pos (steps, then a sine sweep), every other joint holds; the loop runs
like the walk's: at 50 Hz, the IMU sampled by its thread at the walk's rate,
every servo read in one sync read, every goal in one sync write. Per loop it
records the goals sent, the positions read back, the IMU sample used and when
each happened (see mini_bdx_runtime.telemetry).

Goal -> encoder gives the servos' response, encoder -> gyro the IMU's delay
(feet flat, the trunk pitches with the ankles). Swaying the neck on held legs
shakes the trunk on its soles instead, with no joint of the legs moving.
"""

import argparse
import os
import sys
import time

import numpy as np

WALK_SERVICE = "open-duck-walk"
CONTROL_HZ = 50  # the walk's
LEG_KP = 30
HEAD_KP = 8
HEAD_JOINTS = ("neck_pitch", "head_pitch", "head_yaw", "head_roll")
ANKLES = ("left_ankle", "right_ankle")  # same sign both sides for the same motion

SETTLE_S = 2.0
# Ankle offsets from init_pos, rad, each held STEP_HOLD_S: the trunk tilts by
# as much, its feet flat.
STEPS = [0.04, 0.0, -0.04, 0.0, 0.04, 0.0, -0.04, 0.0]
STEP_HOLD_S = 1.0
CHIRP_AMPLITUDE = 0.03  # rad
CHIRP_F0, CHIRP_F1 = 0.2, 3.0  # Hz; 0.4 Hz is the sway canard falls into
CHIRP_S = 20.0
RETURN_S = 1.0

SETTLE, STEP, CHIRP, RETURN = range(4)
RUN_S = SETTLE_S + len(STEPS) * STEP_HOLD_S + CHIRP_S + RETURN_S


def sway(t: float, amplitude: float = 1.0) -> tuple[int, float]:
    """(segment, ankle offset from init_pos, rad) at t s; amplitude scales it."""
    if t < SETTLE_S:
        return SETTLE, 0.0
    t -= SETTLE_S
    if t < len(STEPS) * STEP_HOLD_S:
        return STEP, amplitude * STEPS[int(t // STEP_HOLD_S)]
    t -= len(STEPS) * STEP_HOLD_S
    if t < CHIRP_S:
        k = np.log(CHIRP_F1 / CHIRP_F0) / CHIRP_S
        phase = 2 * np.pi * CHIRP_F0 * (np.exp(k * t) - 1) / k
        # faded in and out over a quarter of the lowest period: no jump
        fade = min(1.0, t * CHIRP_F0 * 4, (CHIRP_S - t) * CHIRP_F0 * 4)
        return CHIRP, amplitude * CHIRP_AMPLITUDE * fade * np.sin(phase)
    return RETURN, 0.0


def _named(names: str) -> list[str]:
    return [n.strip() for n in names.split(",") if n.strip()]


def moved_joints(names: str, joints: list[str]) -> list[str]:
    """The comma-separated joints to sway, each one of the duck's; a leading
    minus sways it the other way."""
    moved = [n.removeprefix("-") for n in _named(names)]
    unknown = [n for n in moved if n not in joints]
    if not moved or unknown:
        raise ValueError(f"unknown joints {unknown}; choose among {joints}")
    return moved


def joint_signs(names: str, joints: list[str]) -> list[float]:
    """Each swayed joint's sign: -1 for a leading minus (the right hip's pitch,
    its axis the left's opposite)."""
    moved_joints(names, joints)
    return [-1.0 if n.startswith("-") else 1.0 for n in _named(names)]


def main() -> None:
    from excite_servos import walk_is_running, walk_service_args
    from mini_bdx_runtime.duck_config import DuckConfig
    from mini_bdx_runtime.raw_imu import Imu
    from mini_bdx_runtime.rustypot_position_hwi import HWI
    from mini_bdx_runtime.telemetry import TelemetryWriter

    service = walk_service_args()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--duck_config_path", default=service.get("duck_config_path"))
    parser.add_argument("--serial_port", default=service.get("serial_port", "/dev/ttyACM0"))
    parser.add_argument("--output_dir", default=os.path.expanduser("~/telemetry"))
    parser.add_argument("--joints", default=",".join(ANKLES),
                        help="the joints swayed together, e.g. neck_pitch to shake the trunk on stiff legs; "
                             "-name sways one the other way (left_hip_pitch,-right_hip_pitch)")
    parser.add_argument("--amplitude", type=float, default=1.0, help="scales the motion")
    parser.add_argument("--leg_kp", type=int, default=LEG_KP)
    parser.add_argument("--head_kp", type=int, default=HEAD_KP)
    parser.add_argument("--imu_hz", type=int, default=CONTROL_HZ,
                        help="IMU thread rate (the walk samples it at its control rate)")
    parser.add_argument("--imu_mode", choices=("ndof", "amg"), default="ndof",
                        help="the BNO055's: fused (the walk's) or raw, with --gyro_bandwidth")
    parser.add_argument("--gyro_bandwidth", type=float, help="Hz, raw mode only (see imu_modes.py)")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--yes", action="store_true", help="don't ask whether it stands")
    args = parser.parse_args()

    if walk_is_running():
        sys.exit(f"The walk is running; stop it first: sudo systemctl stop {WALK_SERVICE}")
    duck_config = DuckConfig(config_json_path=args.duck_config_path) if args.duck_config_path else DuckConfig()
    hwi = HWI(duck_config, args.serial_port)
    joints = list(hwi.joints.keys())
    moved = moved_joints(args.joints, joints)
    swayed = [joints.index(a) for a in moved]
    signs = np.array(joint_signs(args.joints, joints))

    print(f"Swaying {', '.join(moved)} by up to {max(abs(s) for s in STEPS) * args.amplitude:.3f} rad, "
          f"{args.repeats} x {RUN_S:.0f} s. Hold a hand near it.")
    if not args.yes and input("Is the duck standing on its feet? [y/N] ").lower() != "y":
        sys.exit("Aborted.")

    hwi.set_kps([args.head_kp if j in HEAD_JOINTS else args.leg_kp for j in joints])
    hwi.turn_on()
    imu = Imu(sampling_freq=args.imu_hz, orientation=duck_config.imu_orientation,
              calibration=duck_config.imu_calib, mode=args.imu_mode, gyro_bandwidth_hz=args.gyro_bandwidth)

    base = os.path.join(args.output_dir, f"sway_{time.strftime('%Y%m%d_%H%M%S')}")
    rec = TelemetryWriter(
        base,
        [
            ("t", "f8", ()),  # loop start
            ("segment", "u1", ()),  # 0 settle, 1 step, 2 chirp, 3 return
            ("offset", "f4", ()),  # rad, offset sent to the swayed joints
            ("goal", "f4", (14,)),  # rad, without the joints' offsets
            ("t_write", "f8", ()),  # goals written
            ("pos", "f4", (14,)),  # rad, present positions, without the offsets
            ("t_read", "f8", ()),  # positions read
            ("gyro", "f4", (3,)),  # rad/s, the sample the walk would use, walk's axes
            ("accelero", "f4", (3,)),
            ("imu_t", "f8", ()),  # when that sample was read from the BNO055
        ],
        {"kind": "sway", "joints": joints, "moved": moved, "signs": signs.tolist(), "leg_kp": args.leg_kp, "head_kp": args.head_kp, "init_pos": [hwi.init_pos[j] for j in joints],
         "amplitude": args.amplitude, "steps": STEPS, "step_hold_s": STEP_HOLD_S,
         "chirp": {"amplitude": CHIRP_AMPLITUDE, "f0": CHIRP_F0, "f1": CHIRP_F1, "s": CHIRP_S},
         "settle_s": SETTLE_S, "return_s": RETURN_S, "control_hz": CONTROL_HZ, "imu_hz": args.imu_hz, "imu_mode": args.imu_mode, "gyro_bandwidth": args.gyro_bandwidth,
         "repeats": args.repeats},
    )
    print(f"Recording to {base}.bin")
    init = np.array([hwi.init_pos[j] for j in joints])
    period = 1 / CONTROL_HZ
    try:
        for _ in range(args.repeats):
            start = time.time()
            while (now := time.time()) - start < RUN_S:
                segment, offset = sway(now - start, args.amplitude)
                sample = imu.get_data()
                goal = init.copy()
                goal[swayed] += signs * offset
                hwi.set_position_all(dict(zip(joints, goal)))
                t_write = time.time()
                pos = hwi.get_present_positions()
                t_read = time.time()
                rec.write(t=now, segment=segment, offset=offset, goal=goal, t_write=t_write,
                          pos=pos if pos is not None else np.full(14, np.nan), t_read=t_read,
                          gyro=sample["gyro"], accelero=sample["accelero"], imu_t=sample["t"])
                time.sleep(max(0.0, period - (time.time() - now)))
    except KeyboardInterrupt:
        print("Interrupted, back to the standing pose.")
    finally:
        hwi.set_position_all(dict(hwi.init_pos))
        rec.close()
    print(f"Done: {base}.bin. Restart the walk with\n  sudo systemctl start {WALK_SERVICE}")


if __name__ == "__main__":
    main()
