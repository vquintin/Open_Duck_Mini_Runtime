"""canard's STS3215 bus on rustypot 1.x, behind the calls the runtime made on
rustypot 0.1.0's feetech IO (read_present_position, set_kps, ...).

0.1.0 could read only positions and velocities, and its disable_torque left
the torque on (a stopped walk kept holding its pose, 2026-10-21). 1.x's
Sts3215PyController reads everything; the same units: rad, rad/s (measured
on canard against 0.1.0 and against d(position)/dt).
"""

from dataclasses import dataclass
from typing import Any

# present_voltage counts tenths of a volt.
VOLTS_PER_UNIT = 0.1


@dataclass(frozen=True)
class ServoHealth:
    temperature: list[int]  # deg C
    voltage: list[float]  # V
    status: list[int]  # the servo's error bits, 0 when fine


class FeetechBus:
    def __init__(self, io: Any) -> None:
        """io: a rustypot.Sts3215PyController (or anything with its sync_ calls)."""
        self.io = io

    def read_present_position(self, ids: list[int]) -> list[float]:
        return list(self.io.sync_read_present_position(ids))

    def read_present_velocity(self, ids: list[int]) -> list[float]:
        return list(self.io.sync_read_present_speed(ids))

    def write_goal_position(self, ids: list[int], positions: list[float]) -> None:
        self.io.sync_write_goal_position(ids, list(positions))

    def set_kps(self, ids: list[int], kps: list[float]) -> None:
        self.io.sync_write_p_coefficient(ids, [int(k) for k in kps])

    def set_kds(self, ids: list[int], kds: list[float]) -> None:
        self.io.sync_write_d_coefficient(ids, [int(k) for k in kds])

    def enable_torque(self, ids: list[int]) -> None:
        self.io.sync_write_torque_enable(ids, [True] * len(ids))

    def disable_torque(self, ids: list[int]) -> None:
        self.io.sync_write_torque_enable(ids, [False] * len(ids))

    def read_health(self, ids: list[int]) -> ServoHealth:
        """Three sync reads, ~2 ms each on canard's bus."""
        return ServoHealth(
            temperature=[int(t) for t in self.io.sync_read_present_temperature(ids)],
            voltage=[round(v * VOLTS_PER_UNIT, 2) for v in self.io.sync_read_present_voltage(ids)],
            status=[int(s) for s in self.io.sync_read_status(ids)],
        )


class HealthPoller:
    """The walk's view of its servos' health, read one register per step: a sync
    read is ~2 ms of a 20 ms step, so the three are spread over `every` steps."""

    def __init__(self, bus: FeetechBus, ids: list[int], every: int) -> None:
        self.bus, self.ids, self.every = bus, ids, every
        self._step = 0
        self._last: dict[str, list] = {}
        self.health: ServoHealth | None = None  # None until all three were read

    def step(self) -> None:
        phase = self._step % self.every
        self._step += 1
        slots = {0: "temperature", self.every // 3: "voltage", 2 * self.every // 3: "status"}
        if phase not in slots:
            return
        name = slots[phase]
        if name == "temperature":
            self._last[name] = [int(t) for t in self.bus.io.sync_read_present_temperature(self.ids)]
        elif name == "voltage":
            self._last[name] = [round(v * VOLTS_PER_UNIT, 2) for v in self.bus.io.sync_read_present_voltage(self.ids)]
        else:
            self._last[name] = [int(s) for s in self.bus.io.sync_read_status(self.ids)]
        if len(self._last) == 3:
            self.health = ServoHealth(**self._last)
