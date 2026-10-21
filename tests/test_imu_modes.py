import pytest

from mini_bdx_runtime.imu_modes import AMG_MODE, NDOF_MODE, imu_settings


def test_the_walk_keeps_its_fused_mode_by_default():
    assert imu_settings("ndof") == (NDOF_MODE, None, None)


def test_raw_mode_sets_the_gyro_and_accelerometer_bandwidths():
    # BNO055 page 1 GYR_Config_0 bits 5:3 and ACC_Config bits 4:2 (adafruit_bno055's codes)
    assert imu_settings("amg", gyro_bandwidth_hz=116) == (AMG_MODE, 0x10, 0x0C)
    assert imu_settings("amg", gyro_bandwidth_hz=230, accel_bandwidth_hz=125) == (AMG_MODE, 0x08, 0x10)


def test_unknown_settings_are_refused():
    with pytest.raises(ValueError):
        imu_settings("imu")
    with pytest.raises(ValueError):
        imu_settings("amg", gyro_bandwidth_hz=100)
    with pytest.raises(ValueError):
        imu_settings("ndof", gyro_bandwidth_hz=116)  # fusion sets its own filters
