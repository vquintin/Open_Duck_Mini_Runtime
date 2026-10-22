import sys
import types

import pytest

# pygame aborts on import off the duck; the ramp only needs the deadzone.
sys.modules.setdefault("pygame", types.ModuleType("pygame"))
from mini_bdx_runtime.command_ramp import CommandRamp  # noqa: E402

DT = 0.02


def run(ramp, target, steps):
    out = None
    for _ in range(steps):
        out = ramp.step(target)
    return out


def test_a_released_stick_stops_the_walk_in_half_a_second():
    # canard tipped back and fell on sharp stops from 0.15 m/s; ramped over
    # 0.5 s none fell in sim (run27, run30, 2026-10-22)
    r = CommandRamp(DT)
    run(r, (0.15, 0.0, 0.0), 50)
    assert run(r, (0.0, 0.0, 0.0), 10)[0] == pytest.approx(0.15 - 10 * DT * 0.3)
    assert run(r, (0.0, 0.0, 0.0), 15) == (0.0, 0.0, 0.0)


def test_below_the_deadzone_is_zero():
    # the policy never saw a command under the deadzone (0.02 m/s, 0.1 rad/s)
    r = CommandRamp(DT)
    run(r, (0.15, 0.1, 1.0), 100)
    for _ in range(40):
        vx, vy, wz = r.step((0.0, 0.0, 0.0))
        assert vx == 0.0 or abs(vx) >= 0.02
        assert vy == 0.0 or abs(vy) >= 0.02
        assert wz == 0.0 or abs(wz) >= 0.1


def test_a_start_begins_at_the_deadzone():
    r = CommandRamp(DT)
    vx, _, wz = r.step((0.15, 0.0, -1.0))
    assert vx == pytest.approx(0.02 + DT * 0.3)
    assert wz == pytest.approx(-(0.1 + DT * 2.0))


def test_a_reversal_passes_through_zero():
    r = CommandRamp(DT)
    run(r, (0.15, 0.0, 0.0), 50)
    seen = [r.step((-0.15, 0.0, 0.0))[0] for _ in range(60)]
    assert 0.0 in seen
    assert seen[-1] == pytest.approx(-0.15)


def test_reset_drops_to_standing():
    r = CommandRamp(DT)
    run(r, (0.15, 0.1, 1.0), 50)
    r.reset()
    assert r.step((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)
