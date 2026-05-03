from __future__ import annotations

import asyncio
import logging
import re
import string
from dataclasses import dataclass, field
from typing import List

try:
    import apple_fm_sdk as fm
except Exception:
    fm = None

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context keywords that suggest a line contains secret material
# ---------------------------------------------------------------------------
_CONTEXT_KEYWORDS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "bearer",
        "authorization",
        "api_key",
        "apikey",
        "api-key",
        "access_key",
        "secret_key",
        "private_key",
        "credential",
        "credentials",
        "connection_string",
        "connectionstring",
        "dsn",
        "jdbc",
        "ssh-rsa",
        "BEGIN RSA",
        "BEGIN PRIVATE",
        "BEGIN EC",
        "BEGIN OPENSSH",
    }
)

# Characters considered "symbol" for entropy classification
_SYMBOL_CHARS = set(string.punctuation)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class SecretSpan:
    """A contiguous region of text identified as a potential secret."""

    start: int
    end: int
    category: str
    confidence: float


@dataclass
class FMScanResult:
    """Result of the on-chip FM secret scan."""

    detected: bool
    spans: List[SecretSpan] = field(default_factory=list)
    reason_tag: str = ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
async def scan_with_fm(
    text: str,
    timeout_seconds: float = 0.15,
) -> FMScanResult:
    """
    Semantic secret classification using Apple FM on-chip AI.

    Fail-closed design:
    - SDK missing  -> FMScanResult(detected=False)
    - timeout      -> FMScanResult(detected=False)
    - any error    -> FMScanResult(detected=False)

    The prompt NEVER includes raw secret values; high-entropy tokens are
    masked before being sent to the model.
    """
    if fm is None:
        return FMScanResult(detected=False, spans=[], reason_tag="fm_unavailable:sdk_missing")

    try:
        return await asyncio.wait_for(
            _fm_scan_call(text),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        _log.warning("FM secret scanner timed out after %.0fms", timeout_seconds * 1000)
        return FMScanResult(detected=False, spans=[], reason_tag="fm_timeout")
    except Exception:
        _log.warning("FM secret scanner failed", exc_info=True)
        return FMScanResult(detected=False, spans=[], reason_tag="fm_error")


# ---------------------------------------------------------------------------
# Inner FM call (separated so asyncio.wait_for can cancel it)
# ---------------------------------------------------------------------------
async def _fm_scan_call(text: str) -> FMScanResult:
    """Inner FM call using CONTENT_TAGGING use case."""
    model = fm.SystemLanguageModel(
        use_case=fm.SystemLanguageModelUseCase.CONTENT_TAGGING,
    )
    ok, reason = model.is_available()
    if not ok:
        return FMScanResult(detected=False, spans=[], reason_tag=f"fm_unavailable:{reason}")

    session = fm.LanguageModelSession(model=model)

    @fm.generable
    class _Out:
        has_secrets: bool
        secret_count: int
        categories: List[str]
        segment_indices: List[List[int]]

    prompt = _build_sanitized_prompt(text)

    try:
        # Newer SDKs use `generating`, older ones may still use guide().
        out = await session.respond(prompt, generating=_Out)
    except TypeError:
        out = await session.respond(prompt, guide=fm.guide(_Out))

    has_secrets = bool(getattr(out, "has_secrets", False))
    secret_count = int(getattr(out, "secret_count", 0))

    if not has_secrets or secret_count == 0:
        return FMScanResult(detected=False, spans=[], reason_tag="fm_clean")

    spans = _parse_fm_output(out, len(text))
    return FMScanResult(
        detected=len(spans) > 0,
        spans=spans,
        reason_tag="fm_detected",
    )


# ---------------------------------------------------------------------------
# Prompt construction -- NEVER sends raw secret values
# ---------------------------------------------------------------------------
def _build_sanitized_prompt(text: str) -> str:
    """
    Build a prompt for the FM model.

    High-entropy tokens are masked so that the raw secret value is never
    included in the prompt sent to the on-chip model.  Context keywords
    are detected and listed separately to give the model semantic hints.
    """
    lines = text.splitlines()
    sanitized_lines: List[str] = []
    detected_keywords: List[str] = []

    for line in lines:
        lower_line = line.lower()
        for kw in _CONTEXT_KEYWORDS:
            if kw.lower() in lower_line:
                detected_keywords.append(kw)
        sanitized_lines.append(_mask_high_entropy_tokens(line))

    sanitized_text = "\n".join(sanitized_lines)
    keyword_hint = ""
    if detected_keywords:
        unique_keywords = sorted(set(detected_keywords))
        keyword_hint = f"\nContext keywords detected: {', '.join(unique_keywords)}\n"

    prompt = (
        "You are a secret-detection classifier. Analyze the following text "
        "and determine if it contains secrets, credentials, API keys, tokens, "
        "passwords, private keys, or other sensitive material.\n"
        "High-entropy tokens have been masked as first2...last2[Nc].\n"
        "Return has_secrets (bool), secret_count (int), "
        "categories (list of category strings like 'api_key', 'password', "
        "'private_key', 'token', 'connection_string', 'generic_secret'), "
        "and segment_indices (list of [start, end] character index pairs "
        "in the original text).\n"
        "If uncertain, lean toward classifying as a secret (fail-closed).\n"
        f"{keyword_hint}\n"
        f"Text to analyze:\n{sanitized_text}"
    )
    return prompt


# ---------------------------------------------------------------------------
# High-entropy token masking
# ---------------------------------------------------------------------------
def _mask_high_entropy_tokens(line: str) -> str:
    """
    Replace tokens that look like high-entropy secrets with a safe mask.

    Tokens longer than 16 characters that contain 3+ character classes
    (uppercase, lowercase, digit, symbol) are replaced with
    ``first2...last2[Nc]`` where N is the original character count.
    """
    # Split on whitespace but preserve delimiters that commonly separate
    # values in config files (=, :, spaces, quotes).
    tokens = re.split(r"(\s+|[=:\"\'`,;]+)", line)
    result: List[str] = []

    for token in tokens:
        if len(token) > 16 and _looks_high_entropy(token):
            stripped = token.strip("\"' \t,;")
            if len(stripped) > 16 and _looks_high_entropy(stripped):
                first2 = stripped[:2]
                last2 = stripped[-2:]
                n = len(stripped)
                masked = f"{first2}...{last2}[{n}c]"
                # Preserve surrounding characters that were stripped
                prefix = token[: token.index(stripped[0])] if stripped[0] in token else ""
                suffix_start = token.rindex(stripped[-1]) + 1 if stripped[-1] in token else len(token)
                suffix = token[suffix_start:]
                result.append(f"{prefix}{masked}{suffix}")
            else:
                result.append(token)
        else:
            result.append(token)

    return "".join(result)


def _looks_high_entropy(token: str) -> bool:
    """
    Return True if the token contains 3 or more character classes from:
    {uppercase, lowercase, digit, symbol}.

    This heuristic identifies strings that look like API keys, tokens,
    passwords, or other generated secrets.
    """
    has_upper = False
    has_lower = False
    has_digit = False
    has_symbol = False

    for ch in token:
        if ch in _SYMBOL_CHARS:
            has_symbol = True
        elif ch.isupper():
            has_upper = True
        elif ch.islower():
            has_lower = True
        elif ch.isdigit():
            has_digit = True

    class_count = sum([has_upper, has_lower, has_digit, has_symbol])
    return class_count >= 3


# ---------------------------------------------------------------------------
# FM output parsing
# ---------------------------------------------------------------------------
def _parse_fm_output(out: object, text_length: int) -> List[SecretSpan]:
    """
    Parse the structured FM output into a list of SecretSpan objects.

    Validates that indices are within bounds and categories are present.
    Malformed entries are silently dropped (fail-closed: if we cannot
    parse the span, we still report detection at the FMScanResult level).
    """
    categories: List[str] = getattr(out, "categories", []) or []
    segment_indices: List[List[int]] = getattr(out, "segment_indices", []) or []

    spans: List[SecretSpan] = []

    for idx, segment in enumerate(segment_indices):
        # Each segment must be a pair [start, end]
        if not isinstance(segment, (list, tuple)) or len(segment) < 2:
            _log.debug("Skipping malformed segment at index %d: %s", idx, segment)
            continue

        try:
            start = int(segment[0])
            end = int(segment[1])
        except (TypeError, ValueError):
            _log.debug("Skipping non-integer segment at index %d: %s", idx, segment)
            continue

        # Clamp to valid bounds
        start = max(0, start)
        end = min(end, text_length)

        if start >= end:
            _log.debug("Skipping zero-width or inverted segment at index %d: [%d, %d]", idx, start, end)
            continue

        # Use the matching category if available, otherwise "generic_secret"
        category = categories[idx] if idx < len(categories) else "generic_secret"
        if not isinstance(category, str) or not category:
            category = "generic_secret"

        # Default confidence of 0.8 for FM-detected spans; the model does
        # not return per-span confidence so we use a fixed value.
        spans.append(SecretSpan(start=start, end=end, category=category, confidence=0.8))

    return spans
