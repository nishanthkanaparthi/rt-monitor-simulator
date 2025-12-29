from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.sim.scenario import Fault
from src.utils.logging import LogEvent


# =====================
# Configuration
# =====================

class AlarmState(str, Enum):
    NOMINAL = "NOMINAL"
    PENDING_RAISE = "PENDING_RAISE"
    ALARMED = "ALARMED"
    PENDING_CLEAR = "PENDING_CLEAR"


@dataclass(frozen=True)
class AppConfig:
    tick_ms: int = 10
    total_ticks: int = 50

    # Day 6 decision threshold (spike threshold)
    sensor_alarm_threshold: int = 1000

    # Day 7/8 debounce parameters (consecutive ticks required)
    alarm_raise_after: int = 2
    alarm_clear_after: int = 2


# =====================
# Application Logic
# =====================

class App:
    """
    Small monitoring simulator:
    - Emits APP_TICK every tick (tests rely on ordering: APP_TICK must be first)
    - Implements debounced raise/clear behavior for sensor spike alarms
    - Treats dropout (sensor_value=None) as an immediate alarm condition
    - Tracks a finite-state machine for alarm state + emits STATE_TRANSITION logs
    """

    # State machine: allowed transitions (validated by tests/invariants)
    _LEGAL_TRANSITIONS: dict[AlarmState, set[AlarmState]] = {
        AlarmState.NOMINAL: {AlarmState.NOMINAL, AlarmState.PENDING_RAISE, AlarmState.ALARMED},
        AlarmState.PENDING_RAISE: {AlarmState.PENDING_RAISE, AlarmState.NOMINAL, AlarmState.ALARMED},
        AlarmState.ALARMED: {AlarmState.ALARMED, AlarmState.PENDING_CLEAR},
        # While clearing, alarm conditions can return before clear completes
        AlarmState.PENDING_CLEAR: {
            AlarmState.PENDING_CLEAR,
            AlarmState.NOMINAL,
            AlarmState.ALARMED,
            AlarmState.PENDING_RAISE,
        },
    }

    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._tick_count = 0

        # FSM state
        self._state: AlarmState = AlarmState.NOMINAL

        # Debounce streaks
        self._raise_streak = 0
        self._clear_streak = 0

    def _transition(self, now_ms: int, to_state: AlarmState, reason: str) -> list[LogEvent]:
        """
        Transition helper. Emits STATE_TRANSITION if state changes.
        Also validates transitions (tests/invariants depend on this correctness).
        """
        events: list[LogEvent] = []

        from_state = self._state
        if to_state == from_state:
            return events

        allowed = self._LEGAL_TRANSITIONS[from_state]
        assert (
            to_state in allowed
        ), f"Illegal transition {from_state} -> {to_state} (reason={reason})"

        self._state = to_state
        events.append(
            LogEvent(
                t_ms=now_ms,
                level="INFO",
                code="STATE_TRANSITION",
                msg=f"from={from_state} to={to_state} reason={reason}",
            )
        )
        return events

    def tick(self, now_ms: int, faults: list[Fault]) -> list[LogEvent]:
        events: list[LogEvent] = []

        # Always emit APP_TICK first (tests rely on ordering)
        events.append(
            LogEvent(
                t_ms=now_ms,
                level="INFO",
                code="APP_TICK",
                msg=f"tick={self._tick_count}",
            )
        )

        # -------------------------
        # Sensor reading for this tick
        # -------------------------
        sensor_value: int | None = 500  # nominal baseline

        # If multiple faults exist, dropout wins over spike (sensor becomes None)
        for f in faults:
            if f.kind == "dropout":
                sensor_value = None
            elif f.kind == "sensor_spike":
                sensor_value = int(f.value)

        threshold = self._cfg.sensor_alarm_threshold

        # -------------------------
        # Decision logic (FSM + debounce)
        # -------------------------

        # 1) Dropout: immediate alarm condition
        if sensor_value is None:
            # Dropout overrides numeric debounce streaks
            self._raise_streak = 0
            self._clear_streak = 0

            # If we were clearing, dropout means alarm condition returned; go back to ALARMED
            if self._state == AlarmState.PENDING_CLEAR:
                events.extend(self._transition(now_ms, AlarmState.ALARMED, "dropout_returned"))
                events.append(
                    LogEvent(
                        t_ms=now_ms,
                        level="ERROR",
                        code="ALARM_RAISED",
                        msg="reason=sensor_dropout",
                    )
                )

            # If already alarmed, do nothing (no duplicate terminal events)
            elif self._state == AlarmState.ALARMED:
                pass

            # Otherwise, immediate alarm
            else:
                events.extend(self._transition(now_ms, AlarmState.ALARMED, "dropout_immediate"))
                events.append(
                    LogEvent(
                        t_ms=now_ms,
                        level="ERROR",
                        code="ALARM_RAISED",
                        msg="reason=sensor_dropout",
                    )
                )

            self._tick_count += 1
            return events

        # 2) Sensor present: decide spike vs nominal
        is_alarm_condition = sensor_value >= threshold

        if is_alarm_condition:
            # Alarm condition resets clear streak
            self._clear_streak = 0

            # If we were clearing, alarm condition returned before clear completed
            if self._state == AlarmState.PENDING_CLEAR:
                # treat as "raise pending" again (debounced)
                self._raise_streak = 1
                events.extend(self._transition(now_ms, AlarmState.PENDING_RAISE, "raise_pending"))
                events.append(
                    LogEvent(
                        t_ms=now_ms,
                        level="WARN",
                        code="ALARM_PENDING_RAISE",
                        msg=(
                            f"reason=sensor_spike "
                            f"streak={self._raise_streak} needed={self._cfg.alarm_raise_after} "
                            f"value={sensor_value}"
                        ),
                    )
                )

            # If already alarmed, no need to raise again
            elif self._state == AlarmState.ALARMED:
                self._raise_streak = 0

            # If already raising, continue debouncing
            else:
                self._raise_streak += 1
                if self._raise_streak < self._cfg.alarm_raise_after:
                    events.extend(self._transition(now_ms, AlarmState.PENDING_RAISE, "raise_pending"))
                    events.append(
                        LogEvent(
                            t_ms=now_ms,
                            level="WARN",
                            code="ALARM_PENDING_RAISE",
                            msg=(
                                f"reason=sensor_spike "
                                f"streak={self._raise_streak} needed={self._cfg.alarm_raise_after} "
                                f"value={sensor_value}"
                            ),
                        )
                    )
                else:
                    self._raise_streak = 0
                    events.extend(self._transition(now_ms, AlarmState.ALARMED, "raise_committed"))
                    events.append(
                        LogEvent(
                            t_ms=now_ms,
                            level="ERROR",
                            code="ALARM_RAISED",
                            msg=f"reason=sensor_spike value={sensor_value}",
                        )
                    )

        else:
            # Nominal resets raise streak
            self._raise_streak = 0

            # If not alarmed, stay nominal and keep counters sane
            if self._state != AlarmState.ALARMED and self._state != AlarmState.PENDING_CLEAR:
                self._clear_streak = 0
                events.extend(self._transition(now_ms, AlarmState.NOMINAL, "nominal"))

            # If alarmed, we need debounced clear
            else:
                self._clear_streak += 1
                if self._clear_streak < self._cfg.alarm_clear_after:
                    events.extend(self._transition(now_ms, AlarmState.PENDING_CLEAR, "clear_pending"))
                    events.append(
                        LogEvent(
                            t_ms=now_ms,
                            level="INFO",
                            code="ALARM_PENDING_CLEAR",
                            msg=(
                                f"streak={self._clear_streak} needed={self._cfg.alarm_clear_after} "
                                f"value={sensor_value}"
                            ),
                        )
                    )
                else:
                    self._clear_streak = 0
                    events.extend(self._transition(now_ms, AlarmState.NOMINAL, "clear_committed"))
                    events.append(
                        LogEvent(
                            t_ms=now_ms,
                            level="INFO",
                            code="ALARM_CLEARED",
                            msg="reason=nominal",
                        )
                    )

        self._tick_count += 1
        return events
