from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LogEvent:
    t_ms: int
    level: str
    code: str
    msg: str


def format_event(e: LogEvent) -> str:
    return f"t={e.t_ms:06d}ms | {e.level} | {e.code} | {e.msg}"
