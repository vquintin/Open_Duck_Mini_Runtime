"""Time the walk's sensor reads, one after the other against in parallel, and
check the one-read positions and speeds against rustypot's own conversions.

The walk stopped (it owns both buses): sudo systemctl stop open-duck-walk, so
the servos are limp; the duck lies down or is held. Only head_yaw moves, a
slow sine of --amplitude rad under torque, for the speeds to compare; every
other servo stays limp.

  1. head_yaw swayed: the combined read's positions and speeds against
     sync_read_present_position / sync_read_present_speed, read just after;
  2. the reads, --steps times each way: IMU then positions then speeds (the
     walk until 2026-10-24), IMU then one combined read, and the combined
     read on a worker thread while the IMU is read.
"""

import argparse
import sys
import time

import numpy as np

SWAYED = "head_yaw"
SWAY_HZ = 0.5
SWAY_S = 6.0
IGNORE = ["left_antenna", "right_antenna"]


def summary(ms: np.ndarray) -> str:
    return f"median {np.median(ms):5.2f} ms  p90 {np.percentile(ms, 90):5.2f}  p99 {np.percentile(ms, 99):5.2f}  max {ms.max():5.2f}"


def main() -> None:
    from excite_servos import walk_is_running, walk_service_args
    from mini_bdx_runtime.duck_config import DuckConfig
    from mini_bdx_runtime.feetech_bus import RAD_PER_STEP
    from mini_bdx_runtime.parallel_reads import ParallelReads
    from mini_bdx_runtime.raw_imu import Imu
    from mini_bdx_runtime.rustypot_position_hwi import HWI

    service = walk_service_args()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--duck_config_path", default=service.get("duck_config_path"))
    parser.add_argument("--serial_port", default=service.get("serial_port", "/dev/ttyACM0"))
    parser.add_argument("--amplitude", type=float, default=0.15, help="head_yaw's sine, rad")
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--yes", action="store_true", help="don't ask whether the duck is safe")
    args = parser.parse_args()

    if walk_is_running():
        sys.exit("The walk is running; stop it first: sudo systemctl stop open-duck-walk")
    print(f"The servos are limp but {SWAYED}, swayed by {args.amplitude} rad at {SWAY_HZ} Hz.")
    if not args.yes and input("Is the duck lying down or held? [y/N] ").lower() != "y":
        sys.exit("Aborted.")

    duck_config = DuckConfig(config_json_path=args.duck_config_path) if args.duck_config_path else DuckConfig()
    hwi = HWI(duck_config, args.serial_port)
    imu = Imu(50, orientation=duck_config.imu_orientation, calibration=duck_config.imu_calib,
              mode="amg", gyro_bandwidth_hz=116, synchronous=True)
    ids = list(hwi.joints.values())
    swayed = hwi.joints[SWAYED]
    names = list(hwi.joints)

    # 1. the combined read against rustypot's conversions, head_yaw moving
    hwi.io.disable_torque(ids)
    start_pos = hwi.io.read_present_position([swayed])[0]
    hwi.io.enable_torque([swayed])
    dp, dv, v_ref, v_new = [], [], [], []
    try:
        t0 = time.time()
        while (t := time.time() - t0) < SWAY_S:
            hwi.io.write_goal_position([swayed], [start_pos + args.amplitude * np.sin(2 * np.pi * SWAY_HZ * t)])
            pos, vel = hwi.io.read_present_position_and_velocity(ids)
            ref_pos = hwi.io.read_present_position(ids)
            ref_vel = hwi.io.read_present_velocity(ids)
            dp.append(np.subtract(pos, ref_pos))
            dv.append(np.subtract(vel, ref_vel))
            j = names.index(SWAYED)
            v_new.append(vel[j])
            v_ref.append(ref_vel[j])
            time.sleep(0.02)
    finally:
        hwi.io.write_goal_position([swayed], [start_pos])
        time.sleep(0.5)
        hwi.io.disable_torque([swayed])
    dp, dv, v_new, v_ref = np.abs(dp), np.abs(dv), np.array(v_new), np.array(v_ref)
    print(f"positions, combined vs rustypot: max {dp.max() / RAD_PER_STEP:.1f} steps (all servos, {len(dp)} reads)")
    print(f"speeds, combined vs rustypot: max {dv.max():.3f} rad/s; {SWAYED} up to {np.abs(v_ref).max():.2f} rad/s, "
          f"scale {np.dot(v_new, v_ref) / max(np.dot(v_ref, v_ref), 1e-9):.3f}, signs agree {np.mean(np.sign(v_new) == np.sign(v_ref)):.0%}")
    print(f"HWI.combined_read_agrees(): {hwi.combined_read_agrees()}")

    # 2. timings
    reads = ParallelReads()

    def sequential_two():
        imu.get_data()
        hwi.get_present_positions(ignore=IGNORE)
        hwi.get_present_velocities(ignore=IGNORE)

    def sequential_one():
        imu.get_data()
        hwi.get_present_positions_and_velocities(ignore=IGNORE)

    def parallel_one():
        reads.read(lambda: hwi.get_present_positions_and_velocities(ignore=IGNORE), imu.get_data)

    def imu_alone():
        imu.get_data()

    def servos_alone():
        hwi.get_present_positions_and_velocities(ignore=IGNORE)

    for name, fn in (("IMU alone", imu_alone), ("servos, one read, alone", servos_alone),
                     ("IMU, positions, speeds (until now)", sequential_two),
                     ("IMU, then one servo read", sequential_one),
                     ("one servo read || IMU (the walk now)", parallel_one)):
        ms = []
        for _ in range(args.steps):
            s = time.perf_counter()
            fn()
            ms.append((time.perf_counter() - s) * 1000)
            time.sleep(0.01)
        print(f"{name:38s} {summary(np.array(ms))}")
    print(f"IMU rejected samples: {imu.rejected_samples}")
    print("Done. Restart the walk with\n  sudo systemctl start open-duck-walk")


if __name__ == "__main__":
    main()
