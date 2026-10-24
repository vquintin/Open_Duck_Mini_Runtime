"""The servos and the IMU read at once, each on its own bus (the servos' USB
serial, the IMU's bit-banged I2C): one after the other they took ~9 ms on
canard before the policy saw them (2026-10-24), and the IMU sample was that
much older than the encoders' at its first use.

The servos are read on a worker thread while the caller reads the IMU: the
I2C transfer is an ioctl that releases the GIL, so the worker's serial
transfer runs meanwhile whether or not rustypot releases it.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


class ParallelReads:
    def __init__(self) -> None:
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="servo-read")
        # time.monotonic() of the last read's start and of each bus' end
        self.started = self.servos_done = self.imu_done = 0.0

    def _servos(self, read: Callable[[], Any]) -> Any:
        out = read()
        self.servos_done = time.monotonic()
        return out

    def read(self, servos: Callable[[], Any], imu: Callable[[], Any]) -> tuple[Any, Any]:
        """(servos(), imu()), the two run together."""
        self.started = time.monotonic()
        pending = self.pool.submit(self._servos, servos)
        imu_data = imu()
        self.imu_done = time.monotonic()
        return pending.result(), imu_data
