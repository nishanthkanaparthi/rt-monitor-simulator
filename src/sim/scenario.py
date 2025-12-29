from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Fault:
    tick: int
    kind: str
    value: int


@dataclass(frozen=True)
class Scenario:
    name: str
    faults: list[Fault]


def _require_int(data: dict, key: str) -> int:
    v = data.get(key)
    if not isinstance(v, int):
        raise ValueError(f"Scenario field '{key}' must be int")
    return v


def _require_str(data: dict, key: str) -> str:
    v = data.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"Scenario field '{key}' must be non-empty string")
    return v.strip()


def load_scenario(path: str) -> Scenario:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Scenario must be a JSON object")

    name = _require_str(data, "name")

    faults_raw = data.get("faults", [])
    if not isinstance(faults_raw, list):
        raise ValueError("Scenario field 'faults' must be a list")

    faults: list[Fault] = []
    for item in faults_raw:
        if not isinstance(item, dict):
            raise ValueError("Each fault must be an object")
        tick = _require_int(item, "tick")
        kind = _require_str(item, "kind")
        value = _require_int(item, "value")

        if tick < 0:
            raise ValueError("Fault tick must be >= 0")

        faults.append(Fault(tick=tick, kind=kind, value=value))

    return Scenario(name=name, faults=faults)
