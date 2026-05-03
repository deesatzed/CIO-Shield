"""Backfill engine — resolves [CIO:xxxxxx] vault tokens back to originals.

Policy-gated: corporate can restrict which apps can receive backfilled data,
require approval, or disable backfill entirely. Every resolution is audited.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List

from cognitiveio.security.vault_crypto import (
    VAULT_TOKEN_RE_PATTERN,
    decrypt_value,
    extract_token_id,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BackfillResult:
    """Result of a backfill operation."""

    resolved_text: str          # text with tokens replaced by originals
    tokens_found: int           # total [CIO:xxx] tokens found in text
    tokens_resolved: int        # successfully decrypted and replaced
    tokens_denied: int          # denied by policy
    tokens_expired: int         # expired or not found in vault
    tokens_failed: int          # decryption failed
    policy_gate: str            # overall policy decision


# ---------------------------------------------------------------------------
# Token discovery utility
# ---------------------------------------------------------------------------

def find_vault_tokens(text: str) -> List[str]:
    """Find all [CIO:xxxxxx] vault token strings in text."""
    if not text:
        return []
    return re.findall(VAULT_TOKEN_RE_PATTERN, text)


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def backfill_summary(result: BackfillResult) -> str:
    """Human-readable summary of backfill operation."""
    parts: List[str] = []

    parts.append(f"Resolved {result.tokens_resolved}/{result.tokens_found} tokens")

    detail_parts: List[str] = []
    if result.tokens_expired > 0:
        detail_parts.append(f"{result.tokens_expired} expired")
    if result.tokens_denied > 0:
        detail_parts.append(f"{result.tokens_denied} denied")
    if result.tokens_failed > 0:
        detail_parts.append(f"{result.tokens_failed} failed")

    if detail_parts:
        parts.append(f"({', '.join(detail_parts)})")

    parts.append(f"Policy: {result.policy_gate}")

    return " ".join(parts) + "."


# ---------------------------------------------------------------------------
# Core resolve function
# ---------------------------------------------------------------------------

def resolve_tokens(
    text: str,
    store,                      # LocalStore instance
    vault_key: bytes,
    settings=None,              # Settings instance
    policy=None,                # PolicyConstraints (for backfill policy)
    dest_app: str = "",
) -> BackfillResult:
    """Resolve [CIO:xxxxxx] vault tokens in *text* back to their originals.

    Policy checks are applied BEFORE any decryption attempt. If the policy
    denies backfill, the text is returned unchanged but tokens are still
    counted for audit visibility.

    Args:
        text: The text containing vault tokens to resolve.
        store: A LocalStore instance with vault_lookup capability.
        vault_key: The 32-byte AES key for vault decryption.
        settings: Optional Settings instance; checked for vault/backfill flags.
        policy: Optional PolicyConstraints; checked for backfill policy gates.
        dest_app: The destination application requesting backfill.

    Returns:
        BackfillResult with resolved text and detailed counters.
    """
    # Discover tokens in text regardless of policy (needed for audit counts).
    tokens = find_vault_tokens(text)
    tokens_found = len(tokens)

    # ----- Gate 1: Settings-level kill switch -----
    if settings is not None:
        if not getattr(settings, "vault_enabled", True):
            logger.info("Backfill denied: vault disabled in settings")
            return BackfillResult(
                resolved_text=text,
                tokens_found=tokens_found,
                tokens_resolved=0,
                tokens_denied=tokens_found,
                tokens_expired=0,
                tokens_failed=0,
                policy_gate="disabled",
            )
        if not getattr(settings, "vault_backfill_enabled", True):
            logger.info("Backfill denied: vault_backfill disabled in settings")
            return BackfillResult(
                resolved_text=text,
                tokens_found=tokens_found,
                tokens_resolved=0,
                tokens_denied=tokens_found,
                tokens_expired=0,
                tokens_failed=0,
                policy_gate="disabled",
            )

    # ----- Gate 2: Corporate policy -----
    if policy is not None:
        backfill_policy = getattr(policy, "backfill", None)
        if backfill_policy is not None:
            # Policy explicitly disabled.
            if not backfill_policy.enabled:
                logger.info("Backfill denied: corporate policy disabled")
                return BackfillResult(
                    resolved_text=text,
                    tokens_found=tokens_found,
                    tokens_resolved=0,
                    tokens_denied=tokens_found,
                    tokens_expired=0,
                    tokens_failed=0,
                    policy_gate="denied_policy",
                )

            # Approval required but not yet granted (caller would need to
            # implement an approval flow before calling resolve_tokens).
            if backfill_policy.requires_approval:
                logger.info("Backfill denied: corporate policy requires approval")
                return BackfillResult(
                    resolved_text=text,
                    tokens_found=tokens_found,
                    tokens_resolved=0,
                    tokens_denied=tokens_found,
                    tokens_expired=0,
                    tokens_failed=0,
                    policy_gate="requires_approval",
                )

            # App allow-list check.
            allowed_apps = backfill_policy.allowed_apps
            if allowed_apps and dest_app not in allowed_apps:
                logger.info(
                    "Backfill denied: dest_app not in allowed_apps list"
                )
                return BackfillResult(
                    resolved_text=text,
                    tokens_found=tokens_found,
                    tokens_resolved=0,
                    tokens_denied=tokens_found,
                    tokens_expired=0,
                    tokens_failed=0,
                    policy_gate="denied_app",
                )

    # ----- Gate passed: resolve tokens -----
    if tokens_found == 0:
        return BackfillResult(
            resolved_text=text,
            tokens_found=0,
            tokens_resolved=0,
            tokens_denied=0,
            tokens_expired=0,
            tokens_failed=0,
            policy_gate="allowed",
        )

    resolved_text = text
    tokens_resolved = 0
    tokens_expired = 0
    tokens_failed = 0

    for token_str in tokens:
        token_id = extract_token_id(token_str)
        if token_id is None:
            # Regex matched but extract failed — treat as expired/invalid.
            tokens_expired += 1
            continue

        # Look up in vault (handles expiration internally).
        entry = store.vault_lookup(token_id)
        if entry is None:
            tokens_expired += 1
            continue

        # Decrypt the stored value.
        plaintext = decrypt_value(
            ciphertext=entry["encrypted_value"],
            nonce=entry["nonce"],
            tag=entry["tag"],
            vault_key=vault_key,
        )
        if plaintext is None:
            tokens_failed += 1
            logger.warning(
                "Backfill decryption failed for token (count only, no secret logged)"
            )
            continue

        # Replace the first occurrence of this exact token string.
        resolved_text = resolved_text.replace(token_str, plaintext, 1)
        tokens_resolved += 1

    logger.info(
        "Backfill complete: found=%d resolved=%d expired=%d failed=%d",
        tokens_found,
        tokens_resolved,
        tokens_expired,
        tokens_failed,
    )

    return BackfillResult(
        resolved_text=resolved_text,
        tokens_found=tokens_found,
        tokens_resolved=tokens_resolved,
        tokens_denied=0,
        tokens_expired=tokens_expired,
        tokens_failed=tokens_failed,
        policy_gate="allowed",
    )
