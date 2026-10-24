"""raw_imu.Imu read synchronously: the walk reads the BNO055 when it builds its
observation instead of taking a worker's sample up to a step old (canard's was
19.5 ms old in the median, 2026-10-24). Its sensor checks stay, and recovering
the sensor never holds the walk up."""
import sys
import time
from unittest import mock

import numpy as np
import pytest

for name in ("adafruit_bno055", "board", "busio"):  # the hardware's libraries
    sys.modules.setdefault(name, mock.MagicMock())

from mini_bdx_runtime import raw_imu  # noqa: E402


class FakeSensor:
    mode = 0x0C  # NDOF, the mode the Imu asks for


@pytest.fixture
def imu(monkeypatch):
    monkeypatch.setattr(raw_imu, "_init_bno055", lambda mode: FakeSensor())
    started, start = [], raw_imu.Thread.start
    monkeypatch.setattr(raw_imu.Thread, "start", lambda self: (started.append(self._target), start(self)))
    imu = raw_imu.Imu(50, orientation=np.diag([1.0, -1.0, -1.0]), synchronous=True)
    assert started == []  # no worker sampling the sensor on its own
    imu.readings = []
    monkeypatch.setattr(imu, "read_sample", lambda: imu.readings.pop(0))
    return imu


def reading(gyro=(0.1, 0.2, 0.3), accelero=(0.0, 0.0, 9.8)):
    return np.array(gyro), np.array(accelero)


def test_a_synchronous_read_is_taken_when_asked_for(imu):
    imu.readings = [reading()]
    before = time.time()
    data = imu.get_data()
    assert before <= data["t"] <= time.time()
    np.testing.assert_allclose(data["gyro"], [0.1, -0.2, -0.3])  # in the robot's axes
    np.testing.assert_allclose(data["accelero"], [0.0, 0.0, -9.8])


def test_a_failed_read_gives_the_previous_sample(imu):
    imu.readings = [reading()]
    first = imu.get_data()

    def broken():
        raise OSError("I2C transfer failed")

    imu.read_sample = broken
    assert imu.get_data() is first


def test_a_spike_is_dropped(imu):
    imu.readings = [reading(), reading(gyro=(35.5, 0.0, 0.0))]
    first = imu.get_data()
    assert imu.get_data() is first
    assert imu.rejected_samples == 1


def test_recovering_the_sensor_never_holds_the_walk_up(imu, monkeypatch):
    recovering = []
    monkeypatch.setattr(imu, "recover", lambda: (recovering.append(1), time.sleep(0.5)))
    imu.readings = [reading()] + [reading(accelero=(0, 0, 0))] * raw_imu.RECOVER_AFTER_BAD_SAMPLES + [reading()] * 3
    first = imu.get_data()
    start = time.time()
    for _ in range(raw_imu.RECOVER_AFTER_BAD_SAMPLES + 2):
        assert imu.get_data() is first  # the sensor reads nothing, then is being recovered
    assert time.time() - start < 0.2
    assert recovering == [1]
    time.sleep(0.6)
    assert imu.get_data() is not first  # recovered, read again
