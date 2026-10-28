"""A smaller action scale while the walk command is zero, slewed in and out.

canard_walk_12 rocked standing still at 1.6-1.75 Hz, ~4 deg of trunk pitch
(2026-10-28). Replayed in sim, the servos follow their targets as on canard;
the real trunk lags the ankles ~65 deg more (~110 ms): the policy's balance
loop, set on the sim's body, is too strong for the real one. A smaller scale
standing still weakens it. Slewed over SLEW_S, so the targets never jump.
"""

SLEW_S = 0.5


class StandingScale:
    def __init__(self, scale: float, standing_scale: float | None, dt: float) -> None:
        self.scale = scale
        self.standing_scale = scale if standing_scale is None else standing_scale
        self.step_size = abs(scale - self.standing_scale) * dt / SLEW_S
        self.value = scale

    def step(self, command) -> float:
        goal = self.standing_scale if all(c == 0.0 for c in command) else self.scale
        self.value += max(-self.step_size, min(self.step_size, goal - self.value))
        return self.value
