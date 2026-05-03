"""Clipboard Shield — scans text for secrets before paste operations.

This module provides the scanning logic used by both mac mode (real paste
interception) and headless mode (/paste command).  It never stores clipboard
content — only returns scan results.

Three scanning paths are available:

1. **scan_text_for_secrets()** — synchronous, regex-only, backward-compatible.
2. **redact_text_with_tokens()** — replaces secrets with ``[CIO:xxxxxx]``
   vault tokens instead of ``[REDACTED_SECRET]``, storing encrypted originals
   in the local vault for authorized backfill.
3. **scan_text_for_secrets_enhanced()** — async orchestrator combining regex
   tokenized redaction, on-chip FM semantic scanning, and vault storage.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from cognitiveio.security.redaction import SECRET_VALUE_PATTERNS, redact_text

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    """Result of scanning clipboard text for secrets."""

    contains_secrets: bool
    original_length: int
    redacted_text: str
    pattern_ids_matched: List[str] = field(default_factory=list)
    match_count: int = 0

    # Enhanced fields (FM + vault) — defaults preserve backward compat.
    fm_detected: bool = False
    fm_spans: list = field(default_factory=list)  # List of SecretSpan
    fm_reason_tag: str = ""
    vault_token_count: int = 0
    vault_tokens: List[str] = field(default_factory=list)  # token IDs stored


# ---------------------------------------------------------------------------
# 1. Original sync regex-only scanner (UNCHANGED)
# ---------------------------------------------------------------------------

def scan_text_for_secrets(
    text: str,
    extra_patterns: Optional[List[re.Pattern[str]]] = None,
) -> ScanResult:
    """Scan text for secret patterns. Returns ScanResult with redacted version.

    This is the core function used by both mac_bridge (real paste) and
    headless mode (/paste command). It does NOT modify any clipboard — the
    caller decides what to do with the result.
    """
    if not text:
        return ScanResult(
            contains_secrets=False,
            original_length=0,
            redacted_text="",
            match_count=0,
        )

    all_patterns = list(SECRET_VALUE_PATTERNS)
    if extra_patterns:
        all_patterns.extend(extra_patterns)

    match_count = 0
    pattern_ids: List[str] = []

    for i, pattern in enumerate(all_patterns):
        matches = pattern.findall(text)
        if matches:
            match_count += len(matches)
            pattern_ids.append(f"pattern_{i}")

    redacted = redact_text(text, extra_patterns=extra_patterns)
    contains = redacted != text

    return ScanResult(
        contains_secrets=contains,
        original_length=len(text),
        redacted_text=redacted,
        pattern_ids_matched=pattern_ids,
        match_count=match_count,
    )


# ---------------------------------------------------------------------------
# 2. Tokenized redaction — replaces secrets with [CIO:xxxxxx] vault tokens
# ---------------------------------------------------------------------------

def redact_text_with_tokens(
    text: str,
    store,  # LocalStore instance
    vault_key: bytes,
    extra_patterns: Optional[List[re.Pattern[str]]] = None,
    source_app: str = "",
    dest_app: str = "",
    retention_hours: int = 24,
) -> Tuple[str, List[str], int]:
    """Replace secrets with ``[CIO:xxxxxx]`` vault tokens.

    For each regex match the function:
    1. Generates a unique 6-char hex token ID.
    2. Encrypts the original secret value with AES-256-GCM.
    3. Stores the encrypted entry in the local vault.
    4. Replaces the matched text with ``[CIO:xxxxxx]``.

    Returns ``(redacted_text, token_ids, match_count)``.
    """
    from cognitiveio.security.vault_crypto import (
        encrypt_value,
        format_vault_token,
        generate_token_id,
    )

    all_patterns = list(SECRET_VALUE_PATTERNS)
    if extra_patterns:
        all_patterns.extend(extra_patterns)

    # Collect ALL matches with their spans and pattern index.
    # Each entry: (start, end, matched_text, pattern_id_str)
    collected: List[Tuple[int, int, str, str]] = []

    for i, pattern in enumerate(all_patterns):
        for m in pattern.finditer(text):
            collected.append((m.start(), m.end(), m.group(), f"pattern_{i}"))

    if not collected:
        return text, [], 0

    # De-duplicate overlapping spans: keep the longest match at each position.
    # Sort by start ascending, then by span length descending so the first
    # match at a position is the longest.
    collected.sort(key=lambda t: (t[0], -(t[1] - t[0])))

    deduped: List[Tuple[int, int, str, str]] = []
    last_end = -1
    for start, end, matched, pat_id in collected:
        if start < last_end:
            # This span overlaps with an already-accepted span — skip it.
            continue
        deduped.append((start, end, matched, pat_id))
        last_end = end

    # Process replacements in reverse order so string offsets remain valid.
    deduped.sort(key=lambda t: t[0], reverse=True)

    token_ids: List[str] = []
    result_text = text
    now = time.time()

    for start, end, matched, pat_id in deduped:
        token_id = generate_token_id(matched, timestamp=now)
        ciphertext, nonce, tag = encrypt_value(matched, vault_key)

        store.vault_store(
            token_id=token_id,
            encrypted_value=ciphertext,
            nonce=nonce,
            tag=tag,
            pattern_id=pat_id,
            source_app=source_app,
            dest_app=dest_app,
            retention_hours=retention_hours,
        )

        vault_token = format_vault_token(token_id)
        result_text = result_text[:start] + vault_token + result_text[end:]
        token_ids.append(token_id)

    # Reverse token_ids so they are in forward (left-to-right) order.
    token_ids.reverse()

    return result_text, token_ids, len(deduped)


# ---------------------------------------------------------------------------
# 3. FM result merger
# ---------------------------------------------------------------------------

def _merge_fm_results(
    text: str,
    regex_result: ScanResult,
    fm_result,  # FMScanResult
    store=None,
    vault_key: bytes = b"",
    source_app: str = "",
    dest_app: str = "",
    retention_hours: int = 24,
) -> ScanResult:
    """Merge FM-detected spans into an existing regex-based ScanResult.

    FM spans that overlap with regions already redacted by regex (containing
    ``[REDACTED_SECRET]`` or ``[CIO:``) are skipped.  Novel FM-only spans
    are replaced with ``[FM_REDACTED:category]`` in the redacted text.

    If a vault store and key are provided, novel FM spans are also encrypted
    and stored in the vault.
    """
    from cognitiveio.security.vault_crypto import (
        encrypt_value,
        format_vault_token,
        generate_token_id,
    )

    result = ScanResult(
        contains_secrets=regex_result.contains_secrets,
        original_length=regex_result.original_length,
        redacted_text=regex_result.redacted_text,
        pattern_ids_matched=list(regex_result.pattern_ids_matched),
        match_count=regex_result.match_count,
        fm_detected=fm_result.detected,
        fm_spans=list(fm_result.spans),
        fm_reason_tag=fm_result.reason_tag,
        vault_token_count=regex_result.vault_token_count,
        vault_tokens=list(regex_result.vault_tokens),
    )

    if not fm_result.detected or not fm_result.spans:
        return result

    # Build a quick lookup of redacted regions in the *current* redacted text.
    # We check whether the original-text span maps onto already-redacted
    # content by comparing lengths.  A simpler heuristic: if the original text
    # at that span was already captured by regex, the redacted text will
    # contain a replacement token there.  We approximate by checking the
    # original text characters against the redacted text.
    #
    # More robust approach: track which character ranges in the original text
    # have been redacted.  We reconstruct this from the regex match spans.
    already_redacted_ranges: List[Tuple[int, int]] = []
    all_patterns = list(SECRET_VALUE_PATTERNS)
    for pattern in all_patterns:
        for m in pattern.finditer(text):
            already_redacted_ranges.append((m.start(), m.end()))

    # Sort for efficient overlap checks.
    already_redacted_ranges.sort()

    def _overlaps_redacted(start: int, end: int) -> bool:
        """Return True if span [start, end) overlaps any already-redacted range."""
        for rs, re_ in already_redacted_ranges:
            if start < re_ and end > rs:
                return True
        return False

    # Collect novel FM spans (non-overlapping with regex matches).
    novel_spans = []
    for span in fm_result.spans:
        if not _overlaps_redacted(span.start, span.end):
            novel_spans.append(span)

    if not novel_spans:
        # All FM spans were already covered by regex — nothing new to add.
        return result

    # Sort novel spans in reverse order for safe string replacement.
    novel_spans.sort(key=lambda s: s.start, reverse=True)

    # We need to map original-text offsets to redacted-text offsets.
    # The redacted text may have different length due to prior replacements.
    # Strategy: rebuild a character offset map from original -> redacted.
    #
    # For robustness, we re-run replacements on the original text to find
    # the novel regions, then apply FM replacements.  Since novel spans
    # by definition did NOT match any regex, the corresponding text in
    # the redacted output is unchanged from the original.
    #
    # We compute the offset shift caused by prior regex replacements at
    # each position.

    # Build an ordered list of regex replacements (start, end, replacement_len).
    regex_replacements: List[Tuple[int, int, int]] = []
    for pattern in all_patterns:
        for m in pattern.finditer(text):
            regex_replacements.append((m.start(), m.end(), -1))  # -1 = unknown len

    # Determine actual replacement lengths by checking the redacted text.
    # Each regex match was replaced by either [REDACTED_SECRET] (16 chars)
    # or [CIO:xxxxxx] (11 chars).  We detect which by checking the redacted text.
    regex_replacements.sort(key=lambda t: t[0])

    # Compute cumulative offset shift at each replacement boundary.
    cumulative = 0
    redacted_text = regex_result.redacted_text

    # Walk through regex replacements in order and compute the shift.
    shift_entries: List[Tuple[int, int, int]] = []  # (orig_start, orig_end, shift_delta)

    for orig_start, orig_end, _ in regex_replacements:
        orig_len = orig_end - orig_start
        # Find the replacement in redacted text at the corresponding position.
        redacted_pos = orig_start + cumulative
        # The replacement is either [REDACTED_SECRET], {{SECRET:REDACTED}}, or [CIO:xxxxxx].
        # Detect by looking at redacted_text at redacted_pos.
        repl_len = orig_len  # default: no change (should not happen for real matches)
        if redacted_pos < len(redacted_text):
            if redacted_text[redacted_pos:].startswith("[REDACTED_SECRET]"):
                repl_len = len("[REDACTED_SECRET]")
            elif redacted_text[redacted_pos:].startswith("{{SECRET:REDACTED}}"):
                repl_len = len("{{SECRET:REDACTED}}")
            elif redacted_text[redacted_pos:].startswith("[CIO:"):
                repl_len = 11  # [CIO:xxxxxx]
        delta = repl_len - orig_len
        shift_entries.append((orig_start, orig_end, delta))
        cumulative += delta

    def _orig_to_redacted_offset(orig_pos: int) -> int:
        """Map an original-text offset to a redacted-text offset."""
        shift = 0
        for os_, oe_, delta in shift_entries:
            if orig_pos <= os_:
                break
            if orig_pos >= oe_:
                shift += delta
            else:
                # orig_pos is inside a replacement — clamp to start of replacement.
                shift += 0  # map to the start of the replacement region
                break
        return orig_pos + shift

    now = time.time()
    modified_redacted = result.redacted_text

    for span in novel_spans:
        original_value = text[span.start:span.end]
        replacement = f"[FM_REDACTED:{span.category}]"

        # If vault is available, also store the encrypted value.
        if store is not None and vault_key:
            token_id = generate_token_id(original_value, timestamp=now)
            ciphertext, nonce, tag = encrypt_value(original_value, vault_key)
            store.vault_store(
                token_id=token_id,
                encrypted_value=ciphertext,
                nonce=nonce,
                tag=tag,
                pattern_id=f"fm_{span.category}",
                source_app=source_app,
                dest_app=dest_app,
                retention_hours=retention_hours,
            )
            replacement = format_vault_token(token_id)
            result.vault_tokens.append(token_id)
            result.vault_token_count += 1

        # Map original span to redacted-text position.
        r_start = _orig_to_redacted_offset(span.start)
        r_end = _orig_to_redacted_offset(span.end)

        # Safety: clamp to valid bounds.
        r_start = max(0, min(r_start, len(modified_redacted)))
        r_end = max(r_start, min(r_end, len(modified_redacted)))

        modified_redacted = modified_redacted[:r_start] + replacement + modified_redacted[r_end:]

        result.match_count += 1
        result.pattern_ids_matched.append(f"fm_{span.category}")

    result.redacted_text = modified_redacted
    result.contains_secrets = True

    return result


# ---------------------------------------------------------------------------
# 4. Enhanced async scanner (regex + FM + vault)
# ---------------------------------------------------------------------------

async def scan_text_for_secrets_enhanced(
    text: str,
    store=None,          # LocalStore for vault storage (None = skip vault)
    vault_key: bytes = b"",
    settings=None,       # Settings instance (None = use defaults)
    extra_patterns: Optional[List[re.Pattern[str]]] = None,
    source_app: str = "",
    dest_app: str = "",
) -> ScanResult:
    """Enhanced clipboard scanner combining regex, tokenized vault redaction,
    and on-chip FM semantic classification.

    Orchestration logic:

    1. If *text* is empty, return an empty ``ScanResult``.
    2. If *store* and *vault_key* are provided and vault is enabled in
       *settings*, use ``redact_text_with_tokens()`` for tokenized redaction
       that stores encrypted originals in the local vault.
    3. Otherwise fall back to the original ``scan_text_for_secrets()``
       regex-only path for full backward compatibility.
    4. If FM clipboard shield is enabled in *settings*, run
       ``scan_with_fm()`` concurrently and merge any novel detections.
    5. Return an enriched ``ScanResult`` with both regex and FM fields.
    """
    if not text:
        return ScanResult(
            contains_secrets=False,
            original_length=0,
            redacted_text="",
            match_count=0,
        )

    # Resolve settings defaults.
    fm_enabled = True
    fm_timeout = 0.15
    vault_enabled = True
    retention_hours = 24

    if settings is not None:
        fm_enabled = getattr(settings, "fm_clipboard_shield_enabled", True)
        fm_timeout = getattr(settings, "fm_clipboard_shield_timeout_seconds", 0.15)
        vault_enabled = getattr(settings, "vault_enabled", True)
        retention_hours = getattr(settings, "vault_retention_hours", 24)

    # --- Step 1: Regex-based redaction (tokenized or plain) ----------------

    use_vault = store is not None and vault_key and vault_enabled

    if use_vault:
        redacted_text, token_ids, match_count = redact_text_with_tokens(
            text,
            store=store,
            vault_key=vault_key,
            extra_patterns=extra_patterns,
            source_app=source_app,
            dest_app=dest_app,
            retention_hours=retention_hours,
        )

        # Collect pattern IDs for the result (same logic as sync scanner).
        all_patterns = list(SECRET_VALUE_PATTERNS)
        if extra_patterns:
            all_patterns.extend(extra_patterns)

        pattern_ids: List[str] = []
        for i, pattern in enumerate(all_patterns):
            if pattern.search(text):
                pattern_ids.append(f"pattern_{i}")

        contains = redacted_text != text

        regex_result = ScanResult(
            contains_secrets=contains,
            original_length=len(text),
            redacted_text=redacted_text,
            pattern_ids_matched=pattern_ids,
            match_count=match_count,
            vault_token_count=len(token_ids),
            vault_tokens=token_ids,
        )
    else:
        regex_result = scan_text_for_secrets(text, extra_patterns=extra_patterns)

    # --- Step 2: FM semantic scan (if enabled) -----------------------------

    if not fm_enabled:
        return regex_result

    try:
        from cognitiveio.ai.fm_secret_scanner import scan_with_fm

        fm_result = await scan_with_fm(text, timeout_seconds=fm_timeout)
    except ImportError:
        _log.debug("fm_secret_scanner not available; skipping FM scan")
        return regex_result
    except Exception:
        _log.warning("FM scan failed unexpectedly", exc_info=True)
        return regex_result

    # --- Step 3: Merge FM results ------------------------------------------

    if not fm_result.detected:
        # FM found nothing new — attach the clean FM metadata and return.
        regex_result.fm_detected = False
        regex_result.fm_spans = list(fm_result.spans)
        regex_result.fm_reason_tag = fm_result.reason_tag
        return regex_result

    merged = _merge_fm_results(
        text=text,
        regex_result=regex_result,
        fm_result=fm_result,
        store=store if use_vault else None,
        vault_key=vault_key if use_vault else b"",
        source_app=source_app,
        dest_app=dest_app,
        retention_hours=retention_hours,
    )
    return merged
