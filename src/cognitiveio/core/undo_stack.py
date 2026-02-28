from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List
import time
import uuid


@dataclass
class UndoRecord:
    id: str
    ts: float
    app_name: str
    before: str
    after: str
    app_bundle_id: Optional[str] = None
    app_pid: Optional[int] = None
    cursor_pos: Optional[int] = None
    reason_tag: str = "unknown"


class UndoStack:
    def __init__(self, max_size: int = 200):
        self.max_size = max_size
        self._stack: List[UndoRecord] = []

    def push(
        self,
        app_name: str,
        before: str,
        after: str,
        app_bundle_id: Optional[str] = None,
        app_pid: Optional[int] = None,
        cursor_pos: Optional[int] = None,
        reason_tag: str = "unknown",
    ) -> str:
        rec = UndoRecord(
            id=str(uuid.uuid4()),
            ts=time.time(),
            app_name=app_name,
            app_bundle_id=app_bundle_id,
            app_pid=app_pid,
            before=before,
            after=after,
            cursor_pos=cursor_pos,
            reason_tag=reason_tag,
        )
        self._stack.append(rec)
        if len(self._stack) > self.max_size:
            self._stack = self._stack[-self.max_size :]
        return rec.id

    def can_undo(self) -> bool:
        return bool(self._stack)

    def pop(self) -> Optional[UndoRecord]:
        if not self._stack:
            return None
        return self._stack.pop()

    def peek(self) -> Optional[UndoRecord]:
        return self._stack[-1] if self._stack else None
