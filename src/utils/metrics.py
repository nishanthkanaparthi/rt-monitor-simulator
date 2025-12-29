from __future__ import annotations

from dataclasses import dataclass

from src.utils.logging import LogEvent


@dataclass
class RunMetrics:
    alarms_raised: int = 0
    alarms_cleared: int = 0

    # time accounting (ms)
    alarmed_ms: int = 0
    nominal_ms: int = 0

    # fault counters (derived from FAULT_INJECTED events)
    faults_injected: int = 0
    dropout_faults: int = 0
    spike_faults: int = 0

    # clear-time tracking (ms)
    clear_durations_ms_total: int = 0
    clear_durations_count: int = 0

    def mean_time_to_clear_ms(self) -> float | None:
        if self.clear_durations_count == 0:
            return None
        return self.clear_durations_ms_total / self.clear_durations_count


class MetricsCollector:
    """
    Consumes LogEvent stream and produces summary metrics.
    This stays decoupled from App logic: metrics are derived from logs.
    """

    def __init__(self, tick_ms: int) -> None:
        self._tick_ms = tick_ms
        self._m = RunMetrics()

        self._alarmed = False
        self._alarm_start_ms: int | None = None

    def consume(self, e: LogEvent) -> None:
        # Fault injection counters
        if e.code == "FAULT_INJECTED":
            self._m.faults_injected += 1
            if "kind=dropout" in e.msg:
                self._m.dropout_faults += 1
            if "kind=sensor_spike" in e.msg:
                self._m.spike_faults += 1

        # Terminal alarm events
        if e.code == "ALARM_RAISED":
            self._m.alarms_raised += 1
            if not self._alarmed:
                self._alarmed = True
                self._alarm_start_ms = e.t_ms

        if e.code == "ALARM_CLEARED":
            self._m.alarms_cleared += 1
            if self._alarmed and self._alarm_start_ms is not None:
                self._m.clear_durations_ms_total += (e.t_ms - self._alarm_start_ms)
                self._m.clear_durations_count += 1
            self._alarmed = False
            self._alarm_start_ms = None

        # Time accounting: every APP_TICK tells us "one tick elapsed"
        if e.code == "APP_TICK":
            # Attribute this tick duration to current mode
            if self._alarmed:
                self._m.alarmed_ms += self._tick_ms
            else:
                self._m.nominal_ms += self._tick_ms

    def snapshot(self) -> RunMetrics:
        return self._m
