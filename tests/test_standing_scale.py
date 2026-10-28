import pytest

from mini_bdx_runtime.standing_scale import StandingScale

DT = 0.02


def run(s, command, steps):
    out = None
    for _ in range(steps):
        out = s.step(command)
    return out


def test_walking_keeps_the_trained_scale():
    s = StandingScale(0.25, 0.15, DT)
    assert run(s, (0.15, 0.0, 0.0), 10) == 0.25


def test_standing_still_slews_down_to_the_standing_scale():
    # canard_walk_12 rocked standing still at 1.6-1.75 Hz (2026-10-28): its
    # balance loop too strong for the real body; a smaller scale weakens it
    s = StandingScale(0.25, 0.15, DT)
    run(s, (0.15, 0.0, 0.0), 10)
    first = s.step((0.0, 0.0, 0.0))
    assert 0.15 < first < 0.25
    assert first == pytest.approx(0.25 - 0.1 * DT / 0.5)
    assert run(s, (0.0, 0.0, 0.0), 30) == 0.15


def test_a_command_brings_the_trained_scale_back_as_gently():
    s = StandingScale(0.25, 0.15, DT)
    run(s, (0.0, 0.0, 0.0), 50)
    assert s.step((0.0, 0.0, 0.5)) == pytest.approx(0.15 + 0.1 * DT / 0.5)
    assert run(s, (0.0, 0.0, 0.5), 30) == 0.25


def test_off_without_a_standing_scale():
    s = StandingScale(0.25, None, DT)
    assert run(s, (0.0, 0.0, 0.0), 50) == 0.25
