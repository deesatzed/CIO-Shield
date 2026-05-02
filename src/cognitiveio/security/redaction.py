from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from cognitiveio.security.aliases import SECRET_ALIAS_RE

_logger = logging.getLogger(__name__)


def _load_builtin_patterns() -> List[re.Pattern[str]]:
    """Load and compile patterns from the bundled patterns.json file.

    Falls back to an empty list if the file is missing or malformed,
    logging a warning.  This should never happen in a correctly installed
    package.
    """
    patterns_path = Path(__file__).with_name("patterns.json")
    try:
        data = json.loads(patterns_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Failed to load built-in patterns: %s", exc)
        return []

    if not isinstance(data, dict) or "patterns" not in data:
        _logger.warning("Invalid patterns.json format: missing 'patterns' key")
        return []

    compiled: List[re.Pattern[str]] = []
    for entry in data["patterns"]:
        if not isinstance(entry, dict) or "regex" not in entry:
            continue
        try:
            compiled.append(re.compile(entry["regex"]))
        except re.error as exc:
            _logger.warning(
                "Skipping invalid pattern %r: %s",
                entry.get("id", "unknown"),
                exc,
            )
    return compiled


SECRET_VALUE_PATTERNS: List[re.Pattern[str]] = _load_builtin_patterns()


def get_builtin_patterns() -> List[re.Pattern[str]]:
    """Return a copy of the compiled built-in secret patterns.

    Used by audit/events.py to share the same pattern set without duplication.
    """
    return list(SECRET_VALUE_PATTERNS)


def redact_text(
    value: str,
    extra_patterns: Optional[List[re.Pattern[str]]] = None,
) -> str:
    """Redact secret aliases and known secret value patterns from text.

    Corporate policy can inject additional patterns via ``extra_patterns``.
    These are applied *in addition to* the built-in patterns (additive only,
    never subtractive).
    """
    if not value:
        return value

    redacted = SECRET_ALIAS_RE.sub("{{SECRET:REDACTED}}", value)
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    if extra_patterns:
        for pattern in extra_patterns:
            redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def redact_payload(
    payload: Any,
    extra_patterns: Optional[List[re.Pattern[str]]] = None,
) -> Any:
    if isinstance(payload, str):
        return redact_text(payload, extra_patterns=extra_patterns)
    if isinstance(payload, list):
        return [redact_payload(item, extra_patterns=extra_patterns) for item in payload]
    if isinstance(payload, dict):
        out: Dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(k in lowered for k in ("secret", "password", "token", "api_key", "apikey")):
                out[str(key)] = "[REDACTED_SECRET]"
            else:
                out[str(key)] = redact_payload(value, extra_patterns=extra_patterns)
        return out
    return payload
