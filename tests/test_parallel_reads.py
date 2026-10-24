"""The servos read on their own thread while the walk reads the IMU: two
buses (USB serial, bit-banged I2C), each read ~3-5 ms on canard, one after the
other ~9 ms before the policy saw them (2026-10-24)."""
import time

from mini_bdx_runtime.parallel_reads import ParallelReads


def test_both_reads_overlap():
    reads = ParallelReads()
    start = time.monotonic()
    servos, imu = reads.read(lambda: time.sleep(0.05) or "servos", lambda: time.sleep(0.05) or "imu")
    assert (servos, imu) == ("servos", "imu")
    assert time.monotonic() - start < 0.08


def test_the_servos_read_when_they_were_read():
    reads = ParallelReads()
    _, _ = reads.read(lambda: None, lambda: None)
    assert reads.servos_done >= reads.started
    assert reads.imu_done >= reads.started
