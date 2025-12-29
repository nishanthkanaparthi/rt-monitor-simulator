from __future__ import annotations

import pytest

from src.app.app import App, AppConfig, AlarmState
from src.sim.scenario import Fault


def _fault(kind: str, tick: int = 0, value: int = 0) -> Fault:
    # matches your Fault dataclass signature: (tick, kind, value)
    return Fault(tick=tick, kind=kind, value=value)


def test_illegal_transition_is_blocked() -> None:
    """
    This test exists to prove the FSM transition contract is enforced.

    We force an illegal transition (NOMINAL -> PENDING_CLEAR).
    That should raise AssertionError via _transition().
    """
    app = App(AppConfig())

    # Manually violate the transition contract
    with pytest.raises(AssertionError):
        # access the internal helper intentionally (this is a guardrail test)
        app._transition(now_ms=0, to_state=AlarmState.PENDING_CLEAR, reason="test_illegal")  # type: ignore[attr-defined]


def test_dropout_can_force_nominal_to_alarmed() -> None:
    """
    Sanity check: legal fast-path transition still allowed.
    NOMINAL -> ALARMED should be legal for dropout.
    """
    app = App(AppConfig())

    events = app.tick(now_ms=0, faults=[_fault("dropout")])
    assert any(e.code == "ALARM_RAISED" for e in events)
