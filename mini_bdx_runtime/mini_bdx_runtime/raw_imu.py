import contextlib
import struct
import time
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any

import adafruit_bno055
import board
import busio
import numpy as np

from mini_bdx_runtime.imu_modes import NDOF_MODE, imu_settings

# The sensor reports in its own axes; the walk rotates its readings into the
# robot's with the configured orientation (see imu_orientation.py). The chip
# keeps its remap registers across a Pi reboot, so set them back to the
# identity rather than leave whatever an older runtime wrote there.
AXIS_REMAP_NONE = (
    adafruit_bno055.AXIS_REMAP_X,
    adafruit_bno055.AXIS_REMAP_Y,
    adafruit_bno055.AXIS_REMAP_Z,
    adafruit_bno055.AXIS_REMAP_POSITIVE,
    adafruit_bno055.AXIS_REMAP_POSITIVE,
    adafruit_bno055.AXIS_REMAP_POSITIVE,
)

# Delay to let the sensor settle after a mode switch, seconds.
MODE_SETTLE_S = 0.1
# Interval between calibration-status polls, seconds.
CALIBRATION_POLL_S = 0.1
# The worker only keeps the most recent sample.
SAMPLE_QUEUE_SIZE = 1

# One burst read of the data registers instead of the driver's properties:
# imu.gyro and imu.acceleration each read the mode register, then their 6
# bytes, so 4 I2C transfers a sample on the bit-banged bus (296 samples/s
# alone on canard, against 451 burst; far fewer when the walk holds the
# GIL). Accelerometer 0x08-0x0D,
# magnetometer 0x0E-0x13, gyroscope 0x14-0x19: 18 bytes from 0x08.
DATA_REGISTER = 0x08
DATA_LENGTH = 18
ACCELERO_SCALE = 1 / 100  # m/s^2 per LSB
GYRO_SCALE = 0.001090830782496456  # rad/s per LSB (1/16 deg/s)
# The mode register is then checked this often, to notice a sensor reset;
# a reset sensor also reads an all-zero accelerometer, which gravity rules
# out.
MODE_CHECK_PERIOD_S = 0.5
# Consecutive sensor-less samples (0.2 s at 50 Hz) before reconfiguring it.
RECOVER_AFTER_BAD_SAMPLES = 10

# Readings no walking duck produces, i.e. corrupted I2C transfers: the walk
# saw spikes of ~320 m/s^2 and ~35.5 rad/s (the gyro's 2000 dps full scale)
# where it otherwise stays under ~20 m/s^2 and ~3 rad/s.
ACCELERO_MAX_NORM = 6 * 9.81  # m/s^2; NDOF mode measures +/-4 g per axis
GYRO_MAX_NORM = 20.0  # rad/s, ~1150 deg/s
# How many rejected samples to print in full, to see what they look like.
PRINTED_SPIKES = 5


@dataclass(frozen=True)
class ImuCalibration:
    accelerometer: tuple[int, int, int]
    gyroscope: tuple[int, int, int]
    magnetometer: tuple[int, int, int]


def _init_bno055(mode: int = NDOF_MODE) -> adafruit_bno055.BNO055_I2C:
    """Create the BNO055 over I2C in the given mode, in the sensor's own axes."""
    i2c = busio.I2C(board.SCL, board.SDA)
    imu = adafruit_bno055.BNO055_I2C(i2c)
    imu.mode = mode
    imu.axis_remap = AXIS_REMAP_NONE
    return imu


class ImuCalibrator:
    def __init__(self) -> None:
        self.imu = _init_bno055()

    def calibrate(self) -> ImuCalibration:
        while not self.imu.calibrated:
            print("Calibration status: ", self.imu.calibration_status)
            print("Calibrated : ", self.imu.calibrated)
            time.sleep(CALIBRATION_POLL_S)
        print("CALIBRATION DONE")

        imu_calib = ImuCalibration(
            self.imu.offsets_accelerometer,
            self.imu.offsets_gyroscope,
            self.imu.offsets_magnetometer,
        )
        print(f"calibration: {imu_calib}")
        return imu_calib


class Imu:
    def __init__(
        self,
        sampling_freq: int,
        calibration: ImuCalibration | None = None,
        orientation: np.ndarray | None = None,
        mode: str = "ndof",
        gyro_bandwidth_hz: float | None = None,
        accel_bandwidth_hz: float | None = None,
        synchronous: bool = False,
    ) -> None:
        """orientation: the IMU's in the robot frame (v_robot = orientation @
        v_imu, see imu_orientation.py); None reports the sensor's own axes.
        mode: "ndof" (fused, the sensor's filters) or "amg" (raw, with these
        bandwidths; see imu_modes.py). synchronous: get_data() reads the
        sensor itself (one burst, ~2 ms on the bit-banged bus) instead of
        taking a worker's sample, up to a sampling period old."""
        self.mode, self.gyro_bandwidth, self.accel_bandwidth = imu_settings(
            mode, gyro_bandwidth_hz, accel_bandwidth_hz
        )
        self.sampling_freq = sampling_freq
        self.orientation = np.eye(3) if orientation is None else np.asarray(orientation)
        self.calibration = calibration
        self.imu = _init_bno055(self.mode)
        self.apply_calibration()
        self.apply_bandwidths()

        # Spikes dropped since the walk last looked; it resets the count.
        self.rejected_samples = 0
        self.printed_spikes = 0

        self.last_imu_data: dict[str, Any] = {
            "gyro": [0, 0, 0],
            "accelero": [0, 0, 0],
            "t": 0.0,
        }
        self._register = bytes((DATA_REGISTER,))
        self._buffer = bytearray(DATA_LENGTH)
        self.synchronous = synchronous
        self._bad_samples = 0
        self._measuring = True
        self._last_mode_check = 0.0
        self._recovering = Event()  # synchronous: recover() runs on its own thread
        self.imu_queue: Queue = Queue(maxsize=SAMPLE_QUEUE_SIZE)
        if not synchronous:
            Thread(target=self.imu_worker, daemon=True).start()

    def apply_calibration(self) -> None:
        if self.calibration is not None:
            print("Using calibration data")
            self.imu.mode = adafruit_bno055.CONFIG_MODE
            time.sleep(MODE_SETTLE_S)
            print(f"accelerometer calibration: {self.calibration.accelerometer}")
            self.imu.offsets_accelerometer = self.calibration.accelerometer
            print(f"gyroscope calibration: {self.calibration.gyroscope}")
            self.imu.offsets_gyroscope = self.calibration.gyroscope
            print(f"magnetometer calibration: {self.calibration.magnetometer}")
            self.imu.offsets_magnetometer = self.calibration.magnetometer
            self.imu.mode = self.mode
            time.sleep(MODE_SETTLE_S)
        else:
            print("Imu is running uncalibrated")

    def apply_bandwidths(self) -> None:
        """The raw mode's filters (the driver goes through CONFIG mode and back)."""
        if self.gyro_bandwidth is None:
            return
        self.imu.gyro_bandwidth = self.gyro_bandwidth
        self.imu.accel_bandwidth = self.accel_bandwidth
        time.sleep(MODE_SETTLE_S)
        print(f"[IMU]: mode {self.mode:#x}, gyro bandwidth {self.imu.gyro_bandwidth:#x}, "
              f"accelerometer {self.imu.accel_bandwidth:#x}")

    def recover(self) -> None:
        """Put a BNO055 that has fallen out of its mode back to work.

        After a reset (e.g. a supply dip) the sensor boots in CONFIG mode,
        has lost its offsets and the driver reads (None, None, None).
        """
        try:
            print(f"[IMU]: sensor in mode {self.imu.mode:#x}, reconfiguring")
            self.imu.mode = adafruit_bno055.CONFIG_MODE
            time.sleep(MODE_SETTLE_S)
            self.imu.axis_remap = AXIS_REMAP_NONE
            self.apply_calibration()
            self.imu.mode = self.mode
            time.sleep(MODE_SETTLE_S)
            self.apply_bandwidths()
        except Exception as e:
            print("[IMU]: reconfiguration failed:", e)

    def read_sample(self) -> tuple[np.ndarray, np.ndarray]:
        """(gyro, accelerometer) in the sensor's axes, in one I2C transfer."""
        with self.imu.i2c_device as i2c:
            i2c.write_then_readinto(self._register, self._buffer)
        ax, ay, az, _, _, _, gx, gy, gz = struct.unpack("<9h", self._buffer)
        return (
            np.array((gx, gy, gz)) * GYRO_SCALE,
            np.array((ax, ay, az)) * ACCELERO_SCALE,
        )

    def _sample(self) -> dict[str, Any] | None:
        """One reading in the robot's axes, or None: an I2C error, a sensor
        out of its mode (recovered after RECOVER_AFTER_BAD_SAMPLES), a spike."""
        s = time.time()
        try:
            if s - self._last_mode_check >= MODE_CHECK_PERIOD_S:
                self._measuring = self.imu.mode == self.mode
                self._last_mode_check = s
            gyro, accelero = self.read_sample()
        except Exception as e:
            print("[IMU]:", e)
            return None

        # Out of its mode (e.g. reset by a supply dip) the sensor gives
        # no data; never let that reach the policy.
        if not self._measuring or not accelero.any():
            self._last_mode_check = 0.0  # look again at the next sample
            self._bad_samples += 1
            if self._bad_samples == 1:
                print("[IMU]: no data from the sensor")
            if self._bad_samples % RECOVER_AFTER_BAD_SAMPLES == 0:
                if self.synchronous:
                    self._recovering.set()
                    Thread(target=self._recover_in_background, daemon=True).start()
                else:
                    self.recover()
            return None
        if self._bad_samples:
            print(f"[IMU]: data back after {self._bad_samples} bad samples")
            self._bad_samples = 0

        gyro = self.orientation @ gyro
        accelero = self.orientation @ accelero

        # Drop spikes; get_data() then keeps returning the last good
        # sample.
        if (
            np.linalg.norm(gyro) > GYRO_MAX_NORM
            or np.linalg.norm(accelero) > ACCELERO_MAX_NORM
        ):
            self.rejected_samples += 1
            if self.printed_spikes < PRINTED_SPIKES:
                self.printed_spikes += 1
                print(f"[IMU]: rejected spike gyro={gyro} accelero={accelero}")
            return None

        return {
            "gyro": gyro,
            "accelero": accelero,
            "t": s,  # time.time() when the sample was read
        }

    def _recover_in_background(self) -> None:
        try:
            self.recover()
        finally:
            self._last_mode_check = 0.0
            self._recovering.clear()

    def imu_worker(self) -> None:
        while True:
            s = time.time()
            data = self._sample()
            if data is not None:
                # Replace a sample the walk hasn't taken: it gets the freshest.
                with contextlib.suppress(Empty):
                    self.imu_queue.get_nowait()
                self.imu_queue.put(data)
            time.sleep(max(0, 1 / self.sampling_freq - (time.time() - s)))

    def get_data(self) -> dict[str, Any]:
        if self.synchronous:
            if not self._recovering.is_set():
                data = self._sample()
                if data is not None:
                    self.last_imu_data = data
            return self.last_imu_data
        with contextlib.suppress(Exception):
            self.last_imu_data = self.imu_queue.get(False)  # non blocking

        return self.last_imu_data


def bench(seconds: float) -> None:
    """Time the driver's property reads against one burst read."""
    bno = _init_bno055()
    register, buffer = bytes((DATA_REGISTER,)), bytearray(DATA_LENGTH)

    def burst() -> tuple[np.ndarray, np.ndarray]:
        with bno.i2c_device as i2c:
            i2c.write_then_readinto(register, buffer)
        ax, ay, az, _, _, _, gx, gy, gz = struct.unpack("<9h", buffer)
        return np.array((gx, gy, gz)) * GYRO_SCALE, np.array((ax, ay, az)) * ACCELERO_SCALE

    def legacy() -> tuple[np.ndarray, np.ndarray]:
        return np.array(bno.gyro), np.array(bno.acceleration)

    for name, read in (("driver properties", legacy), ("burst read", burst)):
        n, start = 0, time.time()
        while time.time() - start < seconds:
            read()
            n += 1
        elapsed = time.time() - start
        print(f"{name}: {n / elapsed:.0f} samples/s ({elapsed / n * 1000:.1f} ms each)")
    (g1, a1), (g2, a2) = legacy(), burst()
    print(f"same readings: gyro {np.round(g1, 3)} vs {np.round(g2, 3)}, accelero {np.round(a1, 2)} vs {np.round(a2, 2)}")


if __name__ == "__main__":
    import argparse

    PRINT_PERIOD_S = 1 / 25

    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument(
        "--euler_deg",
        type=float,
        nargs=3,
        metavar=("ROLL", "PITCH", "YAW"),
        help="IMU orientation in the robot frame; the sensor's own axes if omitted",
    )
    parser.add_argument("-a", "--accelerometer_offset", type=int, nargs=3)
    parser.add_argument("-g", "--gyroscope_offset", type=int, nargs=3)
    parser.add_argument("-m", "--magnetometer_offset", type=int, nargs=3)
    parser.add_argument(
        "--bench", type=float, metavar="SECONDS", help="time the I2C reads, then exit"
    )

    args = parser.parse_args()
    if args.bench:
        bench(args.bench)
        raise SystemExit

    offsets = (args.accelerometer_offset, args.gyroscope_offset, args.magnetometer_offset)
    imu_calib: ImuCalibration | None = None
    if args.calibrate:
        calibrator = ImuCalibrator()
        imu_calib = calibrator.calibrate()
    elif any(o is not None for o in offsets):
        # Offsets not given default to zero; with none given, run uncalibrated.
        acc, gyro, mag = (tuple(o) if o is not None else (0, 0, 0) for o in offsets)
        imu_calib = ImuCalibration(acc, gyro, mag)

    orientation = None
    if args.euler_deg is not None:
        from mini_bdx_runtime.imu_orientation import from_euler_deg

        orientation = from_euler_deg(*args.euler_deg)
    imu = Imu(50, calibration=imu_calib, orientation=orientation)
    while True:
        data = imu.get_data()
        print("gyro", np.around(data["gyro"], 3))
        print("accelero", np.around(data["accelero"], 3))
        print("---")
        time.sleep(PRINT_PERIOD_S)
