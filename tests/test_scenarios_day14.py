# tests/test_scenarios_day14.py
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def _codes_from_cli_output(out: str) -> list[str]:
    codes: list[str] = []
    for line in out.splitlines():
        # Only parse lines that look like:
        # t=000010ms | INFO | APP_TICK | tick=1
        if " | " not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        # expected: ["t=...", "LEVEL", "CODE", ...]
        if len(parts) >= 3 and parts[0].startswith("t="):
            codes.append(parts[2])
    return codes


def _run_cli_and_get_codes(scenario_path: Path) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "src.main",
        "--tick-ms",
        "10",
        "--ticks",
        "10",
        "--scenario",
        str(scenario_path),
    ]
    out = subprocess.check_output(cmd, text=True)
    return _codes_from_cli_output(out)


def test_scenario_spike_blip_does_not_raise_alarm() -> None:
    """
    A single spike should NOT raise an alarm when alarm_raise_after=2.
    """
    root = Path(__file__).resolve().parents[1]
    scenario = root / "scenarios" / "spike_blip_no_alarm.json"

    codes = _run_cli_and_get_codes(scenario)

    assert "ALARM_RAISED" not in codes, f"Unexpected ALARM_RAISED. codes={codes}"
    # Pending raise is acceptable as observability, but must not become a raise.


def test_scenario_clear_interrupted_by_spike_realarns() -> None:
    """
    Alarm raises, starts clearing, then a spike returns and should re-assert alarm.

    Expected pattern:
      - ALARM_RAISED occurs
      - ALARM_PENDING_CLEAR occurs
      - later, ALARM_RAISED occurs again (alarm condition returns while clearing)
    """
    root = Path(__file__).resolve().parents[1]
    scenario = root / "scenarios" / "clear_interrupted_by_spike.json"

    codes = _run_cli_and_get_codes(scenario)

    assert "ALARM_RAISED" in codes, f"Expected ALARM_RAISED in codes, got: {codes}"
    assert "ALARM_PENDING_CLEAR" in codes, f"Expected ALARM_PENDING_CLEAR in codes, got: {codes}"

    first_clear = codes.index("ALARM_PENDING_CLEAR")

    raised_after_clear = any(
        i > first_clear and c == "ALARM_RAISED"
        for i, c in enumerate(codes)
    )
    assert raised_after_clear, f"Expected a re-raise after pending clear. codes={codes}"
