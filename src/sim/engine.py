from __future__ import annotations

from dataclasses import dataclass

from src.sim.scenario import Fault, Scenario


@dataclass
class ScenarioEngine:
    scenario: Scenario

    def faults_at_tick(self, tick: int) -> list[Fault]:
        out: list[Fault] = []
        for f in self.scenario.faults:
            if f.tick == tick:
                out.append(f)
        return out
