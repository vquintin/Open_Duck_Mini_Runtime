import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sway_delay import RUN_S, SETTLE_S, STEPS, joint_signs, moved_joints, sway  # noqa: E402


def offsets(amplitude=1.0, dt=0.02):
    return np.array([sway(t, amplitude)[1] for t in np.arange(0, RUN_S, dt)])


def test_starts_and_ends_at_the_standing_pose():
    assert sway(0.0) == (0, 0.0)
    assert sway(RUN_S - 0.01)[1] == 0.0


def test_never_past_the_largest_step():
    assert np.abs(offsets()).max() <= max(abs(s) for s in STEPS) + 1e-12
    assert np.abs(offsets(0.5)).max() <= 0.5 * max(abs(s) for s in STEPS) + 1e-12


def test_the_sweep_has_no_jump():
    # past the steps, at the walk's rate, a change no larger than the sweep's top speed allows
    o = offsets()
    sweep = o[int((SETTLE_S + len(STEPS)) / 0.02):]
    assert np.abs(np.diff(sweep)).max() < 0.03 * 2 * np.pi * 3.0 * 0.02 * 1.05


def test_steps_are_held():
    assert sway(SETTLE_S + 0.5) == (1, pytest.approx(STEPS[0]))
    assert sway(SETTLE_S + 2.5)[1] == pytest.approx(STEPS[2])


def test_the_swayed_joints_are_the_ducks():
    joints = ["left_ankle", "neck_pitch", "right_ankle"]
    assert moved_joints("neck_pitch", joints) == ["neck_pitch"]
    assert moved_joints("left_ankle, right_ankle", joints) == ["left_ankle", "right_ankle"]
    with pytest.raises(ValueError):
        moved_joints("neck", joints)
    with pytest.raises(ValueError):
        moved_joints("", joints)


def test_a_minus_sways_a_joint_the_other_way():
    # the hips' pitch axes point opposite ways: the same sway, opposite goals
    joints = ["left_hip_pitch", "right_hip_pitch"]
    assert joint_signs("left_hip_pitch,-right_hip_pitch", joints) == [1.0, -1.0]
    assert moved_joints("left_hip_pitch,-right_hip_pitch", joints) == joints
    with pytest.raises(ValueError):
        moved_joints("-hip", joints)
