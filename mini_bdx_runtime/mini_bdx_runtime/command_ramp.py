"""The walk command (vx, vy, yaw rate) slewed instead of stepped.

A released stick dropped the command from 0.15 m/s to 0 in one step, and
canard tipped back on its heels and fell (2026-10-22). In sim run27 and run30
tip back ~7 deg either way, but fell 3/26 and 5/26 on a sharp stop and 0/26
when it ramped down over 0.5 s.

Commands under the controller's deadzone are never fed: the policy never saw
one (xbox_controller.COMMAND_DEADZONE), so a ramp crosses that band in one step.
"""

from mini_bdx_runtime.xbox_controller import COMMAND_DEADZONE

# vx, vy m/s^2, yaw rad/s^2: 0.15 m/s to 0 in 0.5 s, 1 rad/s in 0.5 s.
SLEW_RATES = (0.3, 0.3, 2.0)


class CommandRamp:
    def __init__(self, dt: float, rates=SLEW_RATES, deadzone=COMMAND_DEADZONE) -> None:
        self.steps = [r * dt for r in rates]
        self.deadzone = deadzone
        self.reset()

    def reset(self) -> None:
        self.value = [0.0, 0.0, 0.0]

    def step(self, target) -> tuple[float, float, float]:
        for i, (goal, step, dz) in enumerate(zip(target, self.steps, self.deadzone)):
            v = self.value[i]
            if v == 0.0 and goal != 0.0:
                v = dz if goal > 0 else -dz  # start from the deadzone's edge
            v += max(-step, min(step, goal - v))
            if abs(v) < dz and (goal == 0.0 or (goal > 0) != (v > 0)):
                v = 0.0  # stopping or reversing: skip the band the policy never saw
            self.value[i] = v
        return tuple(self.value)
