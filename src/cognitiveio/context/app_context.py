from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class AppContext:
    app_name: str
    bundle_id: Optional[str] = None
    window_title: Optional[str] = None
