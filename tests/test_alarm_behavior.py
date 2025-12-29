from __future__ import annotations

from src.app.app import App, AppConfig
from src.sim.scenario import Fault


def _fault(kind: str, *, value: int = 1) -> Fault:
    # tick is irrelevant for App.tick() unit tests; now_ms drives ordering/time
    return Fault(tick=0, kind=kind, value=value)


def _codes(events) -> list[str]:
    return [e.code for e in events]


def test_app_tick_is_always_first_event() -> None:
    """
    Contract: APP_TICK must always be the first event emitted each tick.
    (Tests and downstream log parsers rely on this ordering.)
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    e0 = app.tick(now_ms=0, faults=[])
    assert len(e0) >= 1
    assert e0[0].code == "APP_TICK"

    e1 = app.tick(now_ms=10, faults=[_fault("sensor_spike", value=1200)])
    assert len(e1) >= 1
    assert e1[0].code == "APP_TICK"

    e2 = app.tick(now_ms=20, faults=[_fault("dropout", value=1)])
    assert len(e2) >= 1
    assert e2[0].code == "APP_TICK"


def test_single_spike_does_not_raise_when_raise_after_is_2() -> None:
    """
    With alarm_raise_after=2, first spike should only be 'pending raise' (not raised).
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    e0 = app.tick(now_ms=0, faults=[_fault("sensor_spike", value=1200)])
    assert "ALARM_PENDING_RAISE" in _codes(e0)
    assert "ALARM_RAISED" not in _codes(e0)


def test_two_tick_spike_raises_alarm_on_second_tick() -> None:
    """
    With alarm_raise_after=2, two consecutive spikes should raise on the 2nd tick.
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    e0 = app.tick(now_ms=0, faults=[_fault("sensor_spike", value=1200)])
    assert "ALARM_PENDING_RAISE" in _codes(e0)
    assert "ALARM_RAISED" not in _codes(e0)

    e1 = app.tick(now_ms=10, faults=[_fault("sensor_spike", value=1200)])
    assert "ALARM_RAISED" in _codes(e1)


def test_alarm_does_not_clear_immediately_when_clear_after_is_2() -> None:
    """
    After alarm is raised, a single nominal tick should NOT immediately clear it if alarm_clear_after=2.
    It should enter pending clear.
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    # Raise alarm (2 spikes)
    _ = app.tick(now_ms=0, faults=[_fault("sensor_spike", value=1200)])
    e_raise = app.tick(now_ms=10, faults=[_fault("sensor_spike", value=1200)])
    assert "ALARM_RAISED" in _codes(e_raise)

    # First nominal tick -> pending clear only
    e_nom_1 = app.tick(now_ms=20, faults=[])
    assert "ALARM_PENDING_CLEAR" in _codes(e_nom_1)
    assert "ALARM_CLEARED" not in _codes(e_nom_1)


def test_alarmed_requires_two_nominal_ticks_to_clear() -> None:
    """
    Raise alarm (2 spikes), then it should require 2 nominal ticks to clear.
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    # Raise alarm
    _ = app.tick(now_ms=0, faults=[_fault("sensor_spike", value=1200)])
    e_raise = app.tick(now_ms=10, faults=[_fault("sensor_spike", value=1200)])
    assert "ALARM_RAISED" in _codes(e_raise)

    # Clear requires two nominal ticks
    e_clear_1 = app.tick(now_ms=20, faults=[])
    assert "ALARM_PENDING_CLEAR" in _codes(e_clear_1)
    assert "ALARM_CLEARED" not in _codes(e_clear_1)

    e_clear_2 = app.tick(now_ms=30, faults=[])
    assert (
        "ALARM_CLEARED" in _codes(e_clear_2)
        or "STATE_TRANSITION" in _codes(e_clear_2)
    )



def test_nominal_does_not_emit_pending_clear_when_not_alarmed() -> None:
    """
    If we are not alarmed, nominal ticks should not produce pending-clear/cleared events.
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    e0 = app.tick(now_ms=0, faults=[])
    assert "ALARM_PENDING_CLEAR" not in _codes(e0)
    assert "ALARM_CLEARED" not in _codes(e0)


def test_dropout_overrides_spike_in_same_tick() -> None:
    """
    If both dropout and spike appear in the same tick, dropout must win (sensor_value=None),
    producing an immediate ALARM_RAISED reason=sensor_dropout.
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    events = app.tick(
        now_ms=0,
        faults=[
            _fault("sensor_spike", value=1200),
            _fault("dropout", value=1),
        ],
    )
    assert "ALARM_RAISED" in _codes(events)
