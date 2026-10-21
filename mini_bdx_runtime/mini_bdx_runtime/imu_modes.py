"""The BNO055's operating modes the walk can read its gyro and accelerometer in.

NDOF fuses the three sensors and sets their filters itself; the walk only uses
the gyro and the accelerometer, never the fused orientation. AMG reads them
raw, with filters we choose: a wider gyro bandwidth is a fresher gyro (canard's
standstill sway is the policy's gyro feedback arriving 80-100 ms late, run27
replayed in sim, 2026-10-21), at some noise.

The codes are adafruit_bno055's (GYR_Config_0 bits 5:3, ACC_Config bits 4:2),
kept here so this needs no hardware.
"""

NDOF_MODE = 0x0C
AMG_MODE = 0x07

GYRO_BANDWIDTH = {523: 0x00, 230: 0x08, 116: 0x10, 47: 0x18, 23: 0x20, 12: 0x28, 64: 0x30, 32: 0x38}
ACCEL_BANDWIDTH = {7.81: 0x00, 15.63: 0x04, 31.25: 0x08, 62.5: 0x0C, 125: 0x10, 250: 0x14, 500: 0x18, 1000: 0x1C}
DEFAULT_GYRO_BANDWIDTH_HZ = 116
DEFAULT_ACCEL_BANDWIDTH_HZ = 62.5  # the sensor's default


def imu_settings(
    mode: str, gyro_bandwidth_hz: float | None = None, accel_bandwidth_hz: float | None = None
) -> tuple[int, int | None, int | None]:
    """(operating mode, gyro bandwidth code, accelerometer bandwidth code);
    the codes are None in NDOF, which sets its own."""
    if mode == "ndof":
        if gyro_bandwidth_hz is not None or accel_bandwidth_hz is not None:
            raise ValueError("NDOF sets its own filters")
        return NDOF_MODE, None, None
    if mode != "amg":
        raise ValueError(f"unknown IMU mode {mode!r}: ndof or amg")
    g = DEFAULT_GYRO_BANDWIDTH_HZ if gyro_bandwidth_hz is None else gyro_bandwidth_hz
    a = DEFAULT_ACCEL_BANDWIDTH_HZ if accel_bandwidth_hz is None else accel_bandwidth_hz
    if g not in GYRO_BANDWIDTH:
        raise ValueError(f"gyro bandwidth {g} Hz: one of {sorted(GYRO_BANDWIDTH)}")
    if a not in ACCEL_BANDWIDTH:
        raise ValueError(f"accelerometer bandwidth {a} Hz: one of {sorted(ACCEL_BANDWIDTH)}")
    return AMG_MODE, GYRO_BANDWIDTH[g], ACCEL_BANDWIDTH[a]
