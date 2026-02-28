from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
import json
import time


@dataclass
class LedgerEvent:
    ts: float
    kind: str  # stored | blocked
    reason: str
    app_name: Optional[str] = None
    profile: Optional[str] = None
    event_type: Optional[str] = None
    token_hash: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class PrivacyLedger:
    def __init__(self):
        self._events: List[LedgerEvent] = []

    def log_blocked(
        self,
        reason: str,
        app_name: Optional[str] = None,
        profile: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._events.append(
            LedgerEvent(time.time(), "blocked", reason, app_name=app_name, profile=profile, meta=meta)
        )

    def log_stored(
        self,
        event_type: str,
        app_name: Optional[str] = None,
        profile: Optional[str] = None,
        token_hash: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._events.append(
            LedgerEvent(
                time.time(),
                "stored",
                "stored",
                app_name=app_name,
                profile=profile,
                event_type=event_type,
                token_hash=token_hash,
                meta=meta,
            )
        )

    def counters(self) -> Dict[str, int]:
        c = {"stored": 0, "blocked": 0}
        for e in self._events:
            c[e.kind] = c.get(e.kind, 0) + 1
        return c

    def last(self, n: int = 50) -> List[LedgerEvent]:
        return self._events[-n:]

    def clear(self) -> None:
        self._events.clear()

    def export_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(e) for e in self._events], f, indent=2)
