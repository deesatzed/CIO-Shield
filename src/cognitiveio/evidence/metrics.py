from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import time

@dataclass
class MetricCounters:
    suggestion_shown: int = 0
    suggestion_accepted: int = 0
    suggestion_dismissed: int = 0
    auto_applied: int = 0
    undone: int = 0
    blocked: int = 0

class Metrics:
    def __init__(self):
        self.start_ts = time.time()
        self.c = MetricCounters()

    def inc(self, name: str, n: int = 1):
        if not hasattr(self.c, name):
            raise AttributeError(f"Unknown metric: {name}")
        setattr(self.c, name, getattr(self.c, name) + n)

    def snapshot(self) -> Dict[str, float]:
        elapsed = max(1e-6, time.time() - self.start_ts)
        interruption_rate = self.c.suggestion_shown / (elapsed / 60.0)
        undo_rate = (self.c.undone / self.c.auto_applied) if self.c.auto_applied else 0.0
        accept_rate = (self.c.suggestion_accepted / self.c.suggestion_shown) if self.c.suggestion_shown else 0.0
        dismiss_rate = (self.c.suggestion_dismissed / self.c.suggestion_shown) if self.c.suggestion_shown else 0.0
        return {
            "minutes": elapsed / 60.0,
            "suggestion_shown": self.c.suggestion_shown,
            "suggestion_accepted": self.c.suggestion_accepted,
            "suggestion_dismissed": self.c.suggestion_dismissed,
            "auto_applied": self.c.auto_applied,
            "undone": self.c.undone,
            "blocked": self.c.blocked,
            "interruption_rate_per_min": interruption_rate,
            "undo_rate": undo_rate,
            "accept_rate": accept_rate,
            "dismiss_rate": dismiss_rate,
        }
