"""Audit event dataclasses with validation.

Events are categorical only — NEVER contain secret values, clipboard content,
raw keystrokes, or reconstructable user activity.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from cognitiveio.security.redaction import get_builtin_patterns

# Patterns that should NEVER appear in audit event values.
# Shared with the redaction module to avoid duplication.
_FORBIDDEN_PATTERNS = get_builtin_patterns()


def _contains_secret(value: str) -> bool:
    """Check if a string looks like it contains a secret value."""
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(value):
            return True
    return False


def _validate_no_secrets(data: Dict[str, Any]) -> None:
    """Raise ValueError if any field value appears to contain a secret."""
    for key, value in data.items():
        if isinstance(value, str) and _contains_secret(value):
            raise ValueError(
                f"Audit event field '{key}' appears to contain a secret value. "
                "Audit events must never contain secret data."
            )
        if isinstance(value, dict):
            _validate_no_secrets(value)


@dataclass
class AuditEvent:
    """Base audit event — categorical data only."""

    event: str = ""                     # block, redaction, suggest, trust_circuit, session_summary
    ts: str = ""                        # ISO 8601 timestamp (auto-filled if empty)
    reason: str = ""                    # block reason tag
    app: str = ""                       # destination app name
    profile: str = ""                   # profile classification
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_jsonl(self) -> str:
        """Serialize to a single JSON line, validating no secrets are present."""
        data = {k: v for k, v in asdict(self).items() if v}
        _validate_no_secrets(data)
        return json.dumps(data, separators=(",", ":"))


@dataclass
class ClipboardAuditEvent(AuditEvent):
    """Audit event for clipboard paste operations (image/binary metadata only)."""

    content_type: str = ""              # UTType: public.png, public.tiff, etc.
    pixel_dimensions: str = ""          # e.g. "1920x1080"
    byte_size: int = 0                  # size in bytes
    source_hint: str = ""              # "screenshot" or "copy"
    destination_app: str = ""           # where the paste went

    def __post_init__(self) -> None:
        if not self.event:
            self.event = "clipboard_paste"
        super().__post_init__()


@dataclass
class RedactionAuditEvent(AuditEvent):
    """Audit event when secrets are redacted from clipboard/paste."""

    pattern_type: str = ""              # api_key, aws_key, private_key, corporate_pattern
    destination_profile: str = ""       # profile of destination app
    token_count: int = 0                # how many secrets found (count only)

    def __post_init__(self) -> None:
        if not self.event:
            self.event = "redaction"
        super().__post_init__()


@dataclass
class SessionSummaryEvent(AuditEvent):
    """End-of-session aggregate summary."""

    accept_rate: float = 0.0
    blocks: int = 0
    redactions: int = 0
    duration_seconds: int = 0

    def __post_init__(self) -> None:
        if not self.event:
            self.event = "session_summary"
        super().__post_init__()
