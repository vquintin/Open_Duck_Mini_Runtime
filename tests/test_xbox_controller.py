import sys
import types

import pytest

# pygame aborts on import off the duck (no SDL3 in the x86 build); the stick
# mapping doesn't touch it.
sys.modules.setdefault("pygame", types.ModuleType("pygame"))
from mini_bdx_runtime.xbox_controller import STICK_DEADZONE, stick


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
