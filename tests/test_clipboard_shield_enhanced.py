"""Tests for enhanced clipboard_shield -- tokenized redaction and async FM+regex scanning.

Uses a REAL LocalStore with a temporary SQLite database. NO mocks.
"""
from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path

from cognitiveio.memory.local_store import LocalStore
from cognitiveio.runtime.clipboard_shield import (
    ScanResult,
    redact_text_with_tokens,
    scan_text_for_secrets,
    scan_text_for_secrets_enhanced,
)
from cognitiveio.security.vault_crypto import (
    decrypt_value,
    derive_vault_key,
    extract_token_id,
    VAULT_TOKEN_RE_PATTERN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store() -> LocalStore:
    """Create a real LocalStore with temp database."""
    tmp = tempfile.mktemp(suffix=".db")
    return LocalStore(Path(tmp), encryption_mode="off")


class _Settings:
    vault_enabled = True
    fm_clipboard_shield_enabled = False  # FM SDK unavailable in tests
    fm_clipboard_shield_timeout_seconds = 0.15
    vault_retention_hours = 24


# A secret that reliably matches the openai_api_key pattern: \bsk-[A-Za-z0-9]{20,}\b
_SECRET_SK = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
_SECRET_AWS = "AKIAIOSFODNN7EXAMPLE"
_SECRET_SSN = "123-45-6789"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scan_result_has_new_fields():
    """ScanResult has fm_detected, fm_spans, fm_reason_tag, vault_token_count, vault_tokens."""
    r = ScanResult(
        contains_secrets=False,
        original_length=0,
        redacted_text="",
    )
    assert hasattr(r, "fm_detected")
    assert hasattr(r, "fm_spans")
    assert hasattr(r, "fm_reason_tag")
    assert hasattr(r, "vault_token_count")
    assert hasattr(r, "vault_tokens")
    # Verify default values
    assert r.fm_detected is False
    assert r.fm_spans == []
    assert r.fm_reason_tag == ""
    assert r.vault_token_count == 0
    assert r.vault_tokens == []


def test_scan_result_backward_compatible():
    """scan_text_for_secrets() still works; new fields have defaults."""
    result = scan_text_for_secrets(_SECRET_SK)
    assert result.contains_secrets is True
    assert result.original_length == len(_SECRET_SK)
    assert "[REDACTED_SECRET]" in result.redacted_text
    assert result.match_count >= 1
    # New fields should be at their defaults
    assert result.fm_detected is False
    assert result.fm_spans == []
    assert result.fm_reason_tag == ""
    assert result.vault_token_count == 0
    assert result.vault_tokens == []


def test_redact_text_with_tokens_creates_vault_entries():
    """redact_text_with_tokens replaces secrets with [CIO:...] tokens and populates vault."""
    store = _make_store()
    vault_key = derive_vault_key("test-key")

    redacted, token_ids, match_count = redact_text_with_tokens(
        _SECRET_SK, store=store, vault_key=vault_key,
    )

    # The redacted text should contain a vault token
    assert "[CIO:" in redacted
    assert re.search(VAULT_TOKEN_RE_PATTERN, redacted) is not None
    # Original secret should NOT appear in redacted text
    assert _SECRET_SK not in redacted
    # At least one token should have been created
    assert len(token_ids) > 0
    assert match_count > 0
    # Vault should have entries
    assert store.vault_count() > 0


def test_redact_text_with_tokens_roundtrip():
    """After redaction, look up the token in vault, decrypt, verify original value."""
    store = _make_store()
    vault_key = derive_vault_key("roundtrip-key")

    redacted, token_ids, match_count = redact_text_with_tokens(
        _SECRET_SK, store=store, vault_key=vault_key,
    )

    assert len(token_ids) >= 1, "Expected at least one token id"

    # Look up the first token and decrypt
    token_id = token_ids[0]
    entry = store.vault_lookup(token_id)
    assert entry is not None, f"Vault entry for token {token_id} not found"

    plaintext = decrypt_value(
        ciphertext=entry["encrypted_value"],
        nonce=entry["nonce"],
        tag=entry["tag"],
        vault_key=vault_key,
    )
    assert plaintext == _SECRET_SK


def test_redact_text_with_tokens_clean_text():
    """Clean text returns unchanged, no vault entries."""
    store = _make_store()
    vault_key = derive_vault_key("clean-key")

    text = "This is perfectly clean text with no secrets."
    redacted, token_ids, match_count = redact_text_with_tokens(
        text, store=store, vault_key=vault_key,
    )

    assert redacted == text
    assert token_ids == []
    assert match_count == 0
    assert store.vault_count() == 0


def test_redact_text_with_tokens_multiple_secrets():
    """Text with 3 secrets produces 3 vault tokens."""
    store = _make_store()
    vault_key = derive_vault_key("multi-key")

    text = f"Key1: {_SECRET_SK} and Key2: {_SECRET_AWS} and SSN: {_SECRET_SSN}"
    redacted, token_ids, match_count = redact_text_with_tokens(
        text, store=store, vault_key=vault_key,
    )

    # All three secrets should be replaced with vault tokens
    assert _SECRET_SK not in redacted
    assert _SECRET_AWS not in redacted
    assert _SECRET_SSN not in redacted

    # Count the vault tokens in the redacted text
    vault_tokens_found = re.findall(VAULT_TOKEN_RE_PATTERN, redacted)
    assert len(vault_tokens_found) >= 3, (
        f"Expected at least 3 vault tokens, found {len(vault_tokens_found)} in: {redacted}"
    )

    assert len(token_ids) >= 3
    assert store.vault_count() >= 3


def test_enhanced_scan_with_vault():
    """Enhanced scan with vault enabled creates tokens and detects secrets."""
    store = _make_store()
    vault_key = derive_vault_key("enhanced-key")
    settings = _Settings()

    result = asyncio.run(
        scan_text_for_secrets_enhanced(
            _SECRET_SK,
            store=store,
            vault_key=vault_key,
            settings=settings,
        )
    )

    assert result.contains_secrets is True
    assert result.vault_token_count > 0
    assert len(result.vault_tokens) > 0
    assert "[CIO:" in result.redacted_text
    assert _SECRET_SK not in result.redacted_text


def test_enhanced_scan_clean_text():
    """Enhanced scan on clean text returns contains_secrets=False."""
    store = _make_store()
    vault_key = derive_vault_key("clean-enhanced-key")
    settings = _Settings()

    result = asyncio.run(
        scan_text_for_secrets_enhanced(
            "hello world, nothing secret here",
            store=store,
            vault_key=vault_key,
            settings=settings,
        )
    )

    assert result.contains_secrets is False
    assert result.vault_token_count == 0
    assert result.vault_tokens == []


def test_enhanced_scan_empty_text():
    """Enhanced scan on empty text returns clean result."""
    store = _make_store()
    vault_key = derive_vault_key("empty-key")
    settings = _Settings()

    result = asyncio.run(
        scan_text_for_secrets_enhanced(
            "",
            store=store,
            vault_key=vault_key,
            settings=settings,
        )
    )

    assert result.contains_secrets is False
    assert result.original_length == 0
    assert result.redacted_text == ""
    assert result.match_count == 0


def test_enhanced_scan_no_store_falls_back():
    """Enhanced scan with store=None still detects secrets but vault_token_count=0."""
    settings = _Settings()

    result = asyncio.run(
        scan_text_for_secrets_enhanced(
            _SECRET_SK,
            store=None,
            vault_key=b"",
            settings=settings,
        )
    )

    # Secrets should still be detected via regex fallback
    assert result.contains_secrets is True
    assert _SECRET_SK not in result.redacted_text
    # But no vault tokens since no store provided
    assert result.vault_token_count == 0


def test_enhanced_scan_vault_disabled():
    """Settings with vault_enabled=False falls back to regex only."""
    store = _make_store()
    vault_key = derive_vault_key("disabled-key")

    class _DisabledVaultSettings:
        vault_enabled = False
        fm_clipboard_shield_enabled = False
        fm_clipboard_shield_timeout_seconds = 0.15
        vault_retention_hours = 24

    settings = _DisabledVaultSettings()

    result = asyncio.run(
        scan_text_for_secrets_enhanced(
            _SECRET_SK,
            store=store,
            vault_key=vault_key,
            settings=settings,
        )
    )

    # Secrets detected via regex
    assert result.contains_secrets is True
    assert _SECRET_SK not in result.redacted_text
    # Vault tokens should NOT be created (vault disabled)
    assert result.vault_token_count == 0
    assert store.vault_count() == 0


def test_redact_text_with_tokens_preserves_context():
    """Surrounding text is preserved: 'Hello sk-... goodbye' keeps Hello and goodbye."""
    store = _make_store()
    vault_key = derive_vault_key("context-key")

    text = f"Hello {_SECRET_SK} goodbye"
    redacted, token_ids, match_count = redact_text_with_tokens(
        text, store=store, vault_key=vault_key,
    )

    assert redacted.startswith("Hello ")
    assert redacted.endswith(" goodbye")
    assert _SECRET_SK not in redacted
    assert "[CIO:" in redacted
