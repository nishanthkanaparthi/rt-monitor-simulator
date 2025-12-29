from src.app.app import AppConfig
from src.sim.engine import ScenarioEngine
from src.sim.scenario import Scenario, Fault
from src.main import run_app


def test_fault_injection_is_logged_and_deterministic() -> None:
    cfg = AppConfig(tick_ms=10, total_ticks=5)

    scenario = Scenario(
        name="test",
        faults=[
            Fault(tick=2, kind="sensor_spike", value=900),
        ],
    )
    engine = ScenarioEngine(scenario)

    events = run_app(cfg, engine)

    # sanity: BOOT first
    assert events[0].code == "BOOT"

    # there should be exactly one FAULT_INJECTED
    faults = [e for e in events if e.code == "FAULT_INJECTED"]
    assert len(faults) == 1

    f = faults[0]
    assert f.t_ms == 20  # tick 2 at 10ms per tick
    assert "kind=sensor_spike" in f.msg
    assert "value=900" in f.msg
    assert "tick=2" in f.msg

    # shutdown exists
    assert events[-1].code == "SHUTDOWN"
