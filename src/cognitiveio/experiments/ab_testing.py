from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import socket
from typing import Literal

Variant = Literal["A", "B"]


@dataclass(frozen=True)
class ABConfig:
    salt: str = "cognitiveio-ab-v1"
    state_path: Path = Path.home() / ".cognitiveio" / "ab_variant.txt"


def default_user_key() -> str:
    user = os.getenv("USER") or os.getenv("LOGNAME") or "unknown-user"
    host = socket.gethostname() or "unknown-host"
    return f"{user}@{host}"


def _stable_hash(raw: str) -> int:
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest(), 16)


def assign_variant(user_key: str, cfg: ABConfig) -> Variant:
    path = cfg.state_path
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip().upper()
        if existing in {"A", "B"}:
            return existing  # type: ignore[return-value]

    variant: Variant = "A" if (_stable_hash(f"{cfg.salt}:{user_key}") % 2 == 0) else "B"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(variant, encoding="utf-8")
    return variant
