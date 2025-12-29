from __future__ import annotations

import argparse

from src.app.app import App, AppConfig
from src.sim.clock import SimClock
from src.sim.engine import ScenarioEngine
from src.sim.scenario import load_scenario
from src.utils.logging import LogEvent, format_event
from src.utils.metrics import MetricsCollector


def run_app(cfg: AppConfig, engine: ScenarioEngine) -> list[LogEvent]:
    events: list[LogEvent] = []

    clock = SimClock(tick_ms=cfg.tick_ms, now_ms=0)
    app = App(cfg)

    events.append(
        LogEvent(
            t_ms=0,
            level="INFO",
            code="BOOT",
            msg=f"tick_ms={cfg.tick_ms} total_ticks={cfg.total_ticks}",
        )
    )

    for tick in range(cfg.total_ticks):
        now_ms = clock.now_ms

        # Scenario faults for this tick
        faults = engine.faults_at_tick(tick)
        for fault in faults:
            events.append(
                LogEvent(
                    t_ms=now_ms,
                    level="WARN",
                    code="FAULT_INJECTED",
                    msg=f"kind={fault.kind} value={fault.value} tick={tick}",
                )
            )

        # App tick consumes the faults directly
        events.extend(app.tick(now_ms=now_ms, faults=faults))
        clock.advance()

    events.append(
        LogEvent(
            t_ms=clock.now_ms,
            level="INFO",
            code="SHUTDOWN",
            msg="reason=completed_ticks",
        )
    )

    return events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic monitoring/control simulator")
    parser.add_argument("--tick-ms", type=int, default=10, help="Tick period in milliseconds")
    parser.add_argument("--ticks", type=int, default=50, help="Number of ticks to run")
    parser.add_argument("--scenario", type=str, default="scenarios/demo.json", help="Path to scenario JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    scenario = load_scenario(args.scenario)
    engine = ScenarioEngine(scenario)

    cfg = AppConfig(tick_ms=args.tick_ms, total_ticks=args.ticks)

    events = run_app(cfg, engine)

    # Print event stream
    for e in events:
        print(format_event(e))

    # Collect metrics from logs (derived, not hard-coded into App)
    mc = MetricsCollector(tick_ms=cfg.tick_ms)
    for e in events:
        mc.consume(e)

    m = mc.snapshot()
    mttc = m.mean_time_to_clear_ms()

    # Print metrics summary
    print("---- METRICS ----")
    print(f"alarms_raised={m.alarms_raised}")
    print(f"alarms_cleared={m.alarms_cleared}")
    print(f"faults_injected={m.faults_injected} dropout={m.dropout_faults} spikes={m.spike_faults}")
    print(f"time_nominal_ms={m.nominal_ms} time_alarmed_ms={m.alarmed_ms}")
    print(f"mean_time_to_clear_ms={mttc if mttc is not None else 'n/a'}")


if __name__ == "__main__":
    main()
