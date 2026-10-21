import pytest

from mini_bdx_runtime.feetech_bus import FeetechBus, ServoHealth


class FakeController:
    """rustypot 1.x's Sts3215PyController, as far as the bus uses it."""

    def __init__(self):
        self.writes = []
        self.registers = {"present_position": [0.1, -0.2], "present_speed": [1.5, 0.0],
                          "present_temperature": [38, 55], "present_voltage": [78, 77], "status": [0, 32]}

    def __getattr__(self, name):
        if name.startswith("sync_read_"):
            return lambda ids: self.registers[name.removeprefix("sync_read_")][: len(ids)]
        if name.startswith("sync_write_"):
            return lambda ids, values: self.writes.append((name.removeprefix("sync_write_"), list(ids), list(values)))
        raise AttributeError(name)


@pytest.fixture
def bus():
    return FeetechBus(FakeController())


def test_reads_keep_the_old_api(bus):
    assert bus.read_present_position([20, 13]) == [0.1, -0.2]
    assert bus.read_present_velocity([20, 13]) == [1.5, 0.0]  # rad/s, as 0.1.0's


def test_writes_go_to_every_servo_at_once(bus):
    bus.write_goal_position([20, 13], [0.3, 0.4])
    bus.set_kps([20, 13], [30, 8.0])
    bus.set_kds([20, 13], [0, 0])
    assert bus.io.writes == [("goal_position", [20, 13], [0.3, 0.4]),
                             ("p_coefficient", [20, 13], [30, 8]),
                             ("d_coefficient", [20, 13], [0, 0])]
    assert all(isinstance(v, int) for v in bus.io.writes[1][2])  # the registers take integers


def test_torque_goes_off_and_on(bus):
    bus.disable_torque([20, 13])
    bus.enable_torque([20])
    assert bus.io.writes == [("torque_enable", [20, 13], [False, False]), ("torque_enable", [20], [True])]


def test_health_in_degrees_and_volts(bus):
    h = bus.read_health([20, 13])
    assert h == ServoHealth(temperature=[38, 55], voltage=[7.8, 7.7], status=[0, 32])


def test_health_is_polled_one_register_a_step_about_once_a_second(bus):
    from mini_bdx_runtime.feetech_bus import HealthPoller

    calls = []
    for name in ("present_temperature", "present_voltage", "status"):
        real = getattr(bus.io, "sync_read_" + name)
        bus.io.__dict__["sync_read_" + name] = lambda ids, real=real, name=name: calls.append(name) or real(ids)
    poll = HealthPoller(bus, [20, 13], every=50)
    assert poll.health is None  # nothing read yet
    for step in range(100):
        poll.step()
    assert calls == ["present_temperature", "present_voltage", "status"] * 2  # each once per 50 steps, apart
    assert poll.health == ServoHealth(temperature=[38, 55], voltage=[7.8, 7.7], status=[0, 32])
