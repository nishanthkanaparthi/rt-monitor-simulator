from __future__ import annotations

from dataclasses import asdict

from src.app.app import App, AppConfig
from src.sim.clock import SimClock
from src.sim.engine import ScenarioEngine
from src.sim.scenario import load_scenario
from src.utils.logging import LogEvent


def _run_once(scenario_path: str, *, tick_ms: int, total_ticks: int) -> list[LogEvent]:
    """
    Minimal "full loop" runner for determinism testing.
    Mirrors the structure of main.py/run_app but stays inside the test.
    """
    scenario = load_scenario(scenario_path)
    engine = ScenarioEngine(scenario)

    cfg = AppConfig(tick_ms=tick_ms, total_ticks=total_ticks)
    app = App(cfg)
    clock = SimClock(tick_ms=tick_ms, now_ms=0)

    events: list[LogEvent] = []

    # Basic boot marker to make stream comparison easier
    events.append(
        LogEvent(
            t_ms=0,
            level="INFO",
            code="TEST_BOOT",
            msg=f"scenario={scenario.name} tick_ms={tick_ms} total_ticks={total_ticks}",
        )
    )

    for tick in range(total_ticks):
        now_ms = clock.now_ms

        # Collect faults for this tick from the scenario engine
        faults = engine.faults_at_tick(tick)

        # (Optional) emit fault injection events exactly like the app expects for observability
        for f in faults:
            events.append(
                LogEvent(
                    t_ms=now_ms,
                    level="WARN",
                    code="FAULT_INJECTED",
                    msg=f"kind={f.kind} value={f.value} tick={tick}",
                )
            )

        # Main application tick
        events.extend(app.tick(now_ms=now_ms, faults=faults))

        clock.advance()

    events.append(
        LogEvent(
            t_ms=clock.now_ms,
            level="INFO",
            code="TEST_SHUTDOWN",
            msg="reason=completed_ticks",
        )
    )

    return events


def _normalize(events: list[LogEvent]) -> list[dict]:
    """
    Convert LogEvent dataclasses to plain dicts for stable equality comparisons.
    """
    return [asdict(e) for e in events]


def test_replay_is_deterministic_for_sensor_spike_scenario() -> None:
    path = "scenarios/sensor_spike.json"

    e1 = _normalize(_run_once(path, tick_ms=10, total_ticks=10))
    e2 = _normalize(_run_once(path, tick_ms=10, total_ticks=10))

    assert e1 == e2


def test_replay_is_deterministic_for_dropout_scenario() -> None:
    path = "scenarios/dropout.json"

    e1 = _normalize(_run_once(path, tick_ms=10, total_ticks=10))
    e2 = _normalize(_run_once(path, tick_ms=10, total_ticks=10))

    assert e1 == e2
