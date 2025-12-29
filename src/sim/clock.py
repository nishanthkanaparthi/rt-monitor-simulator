from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SimClock:
    tick_ms: int
    now_ms: int = 0

    def advance(self) -> int:
        """Advance time by one tick and return the new time."""
        self.now_ms += self.tick_ms
        return self.now_ms
