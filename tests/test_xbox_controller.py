import sys
import types

import pytest

# pygame aborts on import off the duck (no SDL3 in the x86 build); the stick
# mapping doesn't touch it.
sys.modules.setdefault("pygame", types.ModuleType("pygame"))
from mini_bdx_runtime.xbox_controller import (
    COMMAND_DEADZONE,
    STICK_DEADZONE,
    head_command,
    stick,
    trigger_yaw,
    walk_command,
)


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


def test_l2_turns_left_and_r2_right():
    assert trigger_yaw(1.0, 0.0) == 1.0
    assert trigger_yaw(0.0, 1.0) == -1.0
    assert trigger_yaw(0.5, 0.5) == 0.0
    assert walk_command(0.0, 0.0, trigger_yaw(1.0, 0.0)) == pytest.approx((0.0, 0.0, 1.0))


def test_a_model_without_head_commands_keeps_the_head_still():
    assert head_command(1.0, -1.0, 0.0) == (0.0, 0.0, 0.0, 0.0)


def test_stick_up_raises_neck_and_head_to_their_stops_together():
    # Open_Duck_Playground's robots/canard.toml [commands]
    assert head_command(1.0, 0.0, 1.0) == pytest.approx((1.1, 0.78, 0.0, 0.0))
    assert head_command(-1.0, 0.0, 1.0) == pytest.approx((-0.34, -0.78, 0.0, 0.0))
    neck, pitch, _, _ = head_command(0.5, 0.0, 1.0)
    assert neck == pytest.approx(0.55) and pitch == pytest.approx(0.39)


def test_stick_left_turns_the_head_left():
    # head_yaw turns about +z: positive is left
    assert head_command(0.0, 1.0, 1.0) == pytest.approx((0.0, 0.0, 1.5, 0.0))
    assert head_command(0.0, -1.0, 1.0) == pytest.approx((0.0, 0.0, -1.5, 0.0))


def test_the_range_factor_scales_every_axis():
    # S9 trains on half the range: the sticks must not leave it
    assert head_command(1.0, 1.0, 0.5) == pytest.approx((0.55, 0.39, 0.75, 0.0))
