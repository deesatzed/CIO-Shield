from __future__ import annotations

import re
from typing import Any, Dict

from cognitiveio.security.aliases import SECRET_ALIAS_RE

SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|password|passphrase|token|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
]


def redact_text(value: str) -> str:
    if not value:
        return value

    redacted = SECRET_ALIAS_RE.sub("{{SECRET:REDACTED}}", value)
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def redact_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return redact_text(payload)
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    if isinstance(payload, dict):
        out: Dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(k in lowered for k in ("secret", "password", "token", "api_key", "apikey")):
                out[str(key)] = "[REDACTED_SECRET]"
            else:
                out[str(key)] = redact_payload(value)
        return out
    return payload
