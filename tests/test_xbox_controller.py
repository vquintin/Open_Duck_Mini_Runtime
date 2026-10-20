import sys
import types

import pytest

# pygame aborts on import off the duck (no SDL3 in the x86 build); the stick
# mapping doesn't touch it.
sys.modules.setdefault("pygame", types.ModuleType("pygame"))
from mini_bdx_runtime.xbox_controller import COMMAND_DEADZONE, STICK_DEADZONE, stick, walk_command


@pytest.mark.parametrize("drift", [0.0, 0.04, -0.03, STICK_DEADZONE])
def test_a_released_stick_reads_zero(drift):
    # canard's right stick rests at 0.03-0.04: a slow turn to the policy
    assert stick(drift) == 0.0


@pytest.mark.parametrize("v", [1.0, -1.0])
def test_the_full_range_is_kept(v):
    assert stick(v) == v


def test_no_jump_past_the_deadzone():
    assert abs(stick(STICK_DEADZONE + 1e-6)) < 1e-4
    assert stick(-0.5) == -stick(0.5)


def test_full_stick_is_the_trained_range():
    assert walk_command(1.0, 1.0, 1.0) == pytest.approx((0.15, 0.1, 1.0))
    assert walk_command(-1.0, -1.0, -1.0) == pytest.approx((-0.15, -0.1, -1.0))


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_walk_commands_below_the_trained_deadzone_are_zero(axis):
    # training zeroes them (Open_Duck_Playground e56235b): the policy never saw one
    sticks = [0.0, 0.0, 0.0]
    full = walk_command(1.0, 1.0, 1.0)[axis]
    sticks[axis] = 0.99 * COMMAND_DEADZONE[axis] / full
    assert walk_command(*sticks)[axis] == 0.0
    sticks[axis] = 1.01 * COMMAND_DEADZONE[axis] / full
    assert walk_command(*sticks)[axis] >= COMMAND_DEADZONE[axis]


def test_the_deadzone_is_per_axis():
    vx, vy, wz = walk_command(1.0, 0.05, 0.0)
    assert vx == pytest.approx(0.15) and vy == 0.0 and wz == 0.0
