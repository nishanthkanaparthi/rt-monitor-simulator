from __future__ import annotations

from src.app.app import App, AppConfig, AlarmState
from src.sim.scenario import Fault


def _fault(kind: str, value: int = 1) -> Fault:
    return Fault(tick=0, kind=kind, value=value)


def _codes(events) -> list[str]:
    return [e.code for e in events]


_ALLOWED: set[AlarmState] = {
    AlarmState.NOMINAL,
    AlarmState.PENDING_RAISE,
    AlarmState.ALARMED,
    AlarmState.PENDING_CLEAR,
}


def _assert_basic_invariants(app: App, events) -> None:
    # 1) State always valid
    assert app._state in _ALLOWED  # intentional: invariant test reaches into internals

    # 2) Counters never negative
    assert app._raise_streak >= 0
    assert app._clear_streak >= 0

    # 3) Never raise and clear in same tick
    codes = _codes(events)
    assert not ("ALARM_RAISED" in codes and "ALARM_CLEARED" in codes)

    # 4) APP_TICK exactly once and first
    assert codes.count("APP_TICK") == 1
    assert codes[0] == "APP_TICK"

    # 5) At most one STATE_TRANSITION per tick
    assert codes.count("STATE_TRANSITION") <= 1


def test_long_run_noise_does_not_raise_alarm() -> None:
    """
    Alternate spike/nominal for a long run.
    With alarm_raise_after=2, this should never raise because spikes are not consecutive.
    Also ensures streak counters don't drift into accidental raises.
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    now_ms = 0
    for i in range(100):
        # spike on even ticks, nominal on odd ticks
        faults = [_fault("sensor_spike", value=1200)] if (i % 2 == 0) else []
        events = app.tick(now_ms=now_ms, faults=faults)

        _assert_basic_invariants(app, events)

        # should never commit raise
        assert "ALARM_RAISED" not in _codes(events)

        now_ms += cfg.tick_ms


def test_long_run_spike_then_nominal_behaves_and_clears() -> None:
    """
    Repeated pattern:
      - 2 spikes -> raise
      - 2 nominal -> clear
    Run many cycles and ensure no illegal drift or double terminal events.
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    now_ms = 0
    raised_count = 0
    cleared_count = 0

    for cycle in range(25):
        # two spikes
        e0 = app.tick(now_ms=now_ms, faults=[_fault("sensor_spike", value=1200)])
        _assert_basic_invariants(app, e0)
        now_ms += cfg.tick_ms

        e1 = app.tick(now_ms=now_ms, faults=[_fault("sensor_spike", value=1200)])
        _assert_basic_invariants(app, e1)
        raised_count += _codes(e1).count("ALARM_RAISED")
        now_ms += cfg.tick_ms

        # two nominals
        e2 = app.tick(now_ms=now_ms, faults=[])
        _assert_basic_invariants(app, e2)
        now_ms += cfg.tick_ms

        e3 = app.tick(now_ms=now_ms, faults=[])
        _assert_basic_invariants(app, e3)
        cleared_count += _codes(e3).count("ALARM_CLEARED")
        now_ms += cfg.tick_ms

    # We should have raised and cleared multiple times (sanity check)
    assert raised_count >= 10
    assert cleared_count >= 10


def test_dropout_immediate_raise_never_double_fires_terminal_event() -> None:
    """
    Dropout should cause immediate raise (if not already alarmed).
    Repeating dropout ticks should not emit ALARM_RAISED every tick once already ALARMED.
    """
    cfg = AppConfig(alarm_raise_after=2, alarm_clear_after=2, sensor_alarm_threshold=1000)
    app = App(cfg)

    now_ms = 0
    raised_total = 0

    # first dropout: should raise
    e0 = app.tick(now_ms=now_ms, faults=[_fault("dropout", value=1)])
    _assert_basic_invariants(app, e0)
    raised_total += _codes(e0).count("ALARM_RAISED")
    now_ms += cfg.tick_ms

    # continue dropout for a while: should not raise again and again
    for _ in range(20):
        e = app.tick(now_ms=now_ms, faults=[_fault("dropout", value=1)])
        _assert_basic_invariants(app, e)
        raised_total += _codes(e).count("ALARM_RAISED")
        now_ms += cfg.tick_ms

    # should be exactly 1 raise across repeated dropout ticks
    assert raised_total == 1
