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

    # Day 6: decision threshold
    sensor_alarm_threshold: int = 1000

    # Day 7/8: debounce parameters (how many consecutive ticks required)
    alarm_raise_after: int = 2
    alarm_clear_after: int = 2


# =====================
# Application Logic
# =====================

class App:
    # Allowed state machine moves (Day 11 invariant tests rely on this)
    _LEGAL_TRANSITIONS: dict[AlarmState, set[AlarmState]] = {
        AlarmState.NOMINAL: {AlarmState.NOMINAL, AlarmState.PENDING_RAISE, AlarmState.ALARMED},
        AlarmState.PENDING_RAISE: {AlarmState.PENDING_RAISE, AlarmState.NOMINAL, AlarmState.ALARMED},
        AlarmState.ALARMED: {AlarmState.ALARMED, AlarmState.PENDING_CLEAR},
        # IMPORTANT: allow PENDING_CLEAR -> PENDING_RAISE when alarm condition returns while clearing
        AlarmState.PENDING_CLEAR: {AlarmState.PENDING_CLEAR, AlarmState.NOMINAL, AlarmState.PENDING_RAISE},
    }

    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._tick_count = 0

        # Current committed state (Day 9+)
        self._state: AlarmState = AlarmState.NOMINAL

        # Legacy boolean kept in sync (if any older code reads it)
        self._alarm_active = False

        # Debounce streaks (Day 7/8)
        self._raise_streak = 0
        self._clear_streak = 0

    def _transition(self, now_ms: int, to_state: AlarmState, reason: str) -> list[LogEvent]:
        events: list[LogEvent] = []

        from_state = self._state
        if to_state == from_state:
            return events

        allowed = self._LEGAL_TRANSITIONS[from_state]
        assert to_state in allowed, (
            f"Illegal transition {from_state} -> {to_state} (reason={reason})"
        )

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

        # Always emit APP_TICK first (tests rely on this ordering)
        events.append(
            LogEvent(
                t_ms=now_ms,
                level="INFO",
                code="APP_TICK",
                msg=f"tick={self._tick_count}",
            )
        )

        # Nominal baseline sensor
        sensor_value: int | None = 500

        # If multiple faults exist, dropout wins over spike (sensor becomes None)
        for f in faults:
            if f.kind == "dropout":
                sensor_value = None
            elif f.kind == "sensor_spike":
                sensor_value = int(f.value)

        # Alarm condition?
        alarm_condition = False
        if sensor_value is None:
            alarm_condition = True
        else:
            alarm_condition = sensor_value >= self._cfg.sensor_alarm_threshold

        # -------------------------
        # Decision logic (state machine)
        # -------------------------

        # Dropout: treat as immediate alarm condition (no debounce)
        if sensor_value is None:
            # Reset debounce counters for numeric logic
            self._raise_streak = 0
            self._clear_streak = 0

            # If we're not already alarmed, go to ALARMED immediately
            if self._state != AlarmState.ALARMED:
                events.extend(self._transition(now_ms, AlarmState.ALARMED, "dropout_immediate"))
                events.append(
                    LogEvent(
                        t_ms=now_ms,
                        level="ERROR",
                        code="ALARM_RAISED",
                        msg="reason=sensor_dropout",
                    )
                )

            self._alarm_active = (self._state == AlarmState.ALARMED)
            self._tick_count += 1
            return events

        # Sensor is present (numeric)
        if alarm_condition:
            # If we're in the middle of clearing, alarm condition returned:
            # go back to PENDING_RAISE (this is what the invariant test expects).
            if self._state == AlarmState.PENDING_CLEAR:
                self._clear_streak = 0
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

            # If already alarmed, just keep counters sane
            elif self._state == AlarmState.ALARMED:
                self._clear_streak = 0

            else:
                # Debounced raise path
                self._clear_streak = 0
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
                    # Commit raise
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
            # Nominal path: can clear alarm with debounce
            if self._state != AlarmState.ALARMED and self._state != AlarmState.PENDING_CLEAR:
                # Not in alarm: keep counters sane and stay nominal
                self._raise_streak = 0
                self._clear_streak = 0
                events.extend(self._transition(now_ms, AlarmState.NOMINAL, "nominal"))
            else:
                # Debounced clear path
                self._raise_streak = 0
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
                    # Commit clear
                    events.extend(self._transition(now_ms, AlarmState.NOMINAL, "clear_committed"))
                    events.append(
                        LogEvent(
                            t_ms=now_ms,
                            level="INFO",
                            code="ALARM_CLEARED",
                            msg="reason=nominal",
                        )
                    )

        # Keep legacy boolean in sync in one place
        self._alarm_active = (self._state == AlarmState.ALARMED)

        self._tick_count += 1
        return events
