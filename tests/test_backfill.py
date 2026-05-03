"""Tests for backfill.py -- policy-gated vault token resolution.

Uses REAL LocalStore, REAL encryption, REAL vault storage. NO mocks.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from cognitiveio.memory.local_store import LocalStore
from cognitiveio.runtime.backfill import (
    BackfillResult,
    backfill_summary,
    find_vault_tokens,
    resolve_tokens,
)
from cognitiveio.runtime.clipboard_shield import redact_text_with_tokens
from cognitiveio.security.vault_crypto import derive_vault_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store() -> LocalStore:
    """Create a real LocalStore with temp database."""
    tmp = tempfile.mktemp(suffix=".db")
    return LocalStore(Path(tmp), encryption_mode="off")


class _Settings:
    vault_enabled = True
    vault_backfill_enabled = True
    vault_retention_hours = 24


class _DisabledSettings:
    vault_enabled = False
    vault_backfill_enabled = False


class _BackfillPolicy:
    enabled = True
    retention_hours = 24
    allowed_apps = frozenset()
    requires_approval = False


class _DeniedAppPolicy:
    enabled = True
    retention_hours = 24
    allowed_apps = frozenset({"Terminal", "Xcode"})
    requires_approval = False


class _DisabledPolicy:
    enabled = False
    retention_hours = 24
    allowed_apps = frozenset()
    requires_approval = False


class _ApprovalPolicy:
    enabled = True
    retention_hours = 24
    allowed_apps = frozenset()
    requires_approval = True


class _PolicyConstraints:
    def __init__(self, backfill):
        self.backfill = backfill


# A secret that reliably matches the openai_api_key pattern
_SECRET_SK = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_find_vault_tokens_finds_tokens():
    """find_vault_tokens detects [CIO:xxxxxx] tokens in text."""
    tokens = find_vault_tokens("text [CIO:a1b2c3] more [CIO:d4e5f6]")
    assert len(tokens) == 2
    assert "[CIO:a1b2c3]" in tokens
    assert "[CIO:d4e5f6]" in tokens


def test_find_vault_tokens_no_tokens():
    """find_vault_tokens returns empty list for normal text."""
    tokens = find_vault_tokens("normal text with no vault tokens")
    assert tokens == []


def test_find_vault_tokens_empty_text():
    """find_vault_tokens returns empty list for empty string."""
    tokens = find_vault_tokens("")
    assert tokens == []


def test_backfill_result_dataclass():
    """BackfillResult fields exist and are properly typed."""
    r = BackfillResult(
        resolved_text="test",
        tokens_found=3,
        tokens_resolved=2,
        tokens_denied=0,
        tokens_expired=1,
        tokens_failed=0,
        policy_gate="allowed",
    )
    assert r.resolved_text == "test"
    assert r.tokens_found == 3
    assert r.tokens_resolved == 2
    assert r.tokens_denied == 0
    assert r.tokens_expired == 1
    assert r.tokens_failed == 0
    assert r.policy_gate == "allowed"


def test_backfill_summary_format():
    """Verify human-readable summary output format."""
    r = BackfillResult(
        resolved_text="resolved",
        tokens_found=5,
        tokens_resolved=3,
        tokens_denied=1,
        tokens_expired=1,
        tokens_failed=0,
        policy_gate="allowed",
    )
    summary = backfill_summary(r)
    assert "3/5" in summary
    assert "Policy: allowed" in summary
    assert "1 expired" in summary
    assert "1 denied" in summary
    assert summary.endswith(".")


def test_resolve_tokens_full_roundtrip():
    """Create vault entries via redact_text_with_tokens, then resolve_tokens to recover originals."""
    store = _make_store()
    vault_key = derive_vault_key("roundtrip-key")
    settings = _Settings()
    policy = _PolicyConstraints(_BackfillPolicy())

    original_text = f"Here is a key: {_SECRET_SK} end"
    redacted, token_ids, match_count = redact_text_with_tokens(
        original_text, store=store, vault_key=vault_key,
    )

    # Verify redaction happened
    assert _SECRET_SK not in redacted
    assert "[CIO:" in redacted
    assert match_count >= 1

    # Now resolve the tokens back
    result = resolve_tokens(
        redacted,
        store=store,
        vault_key=vault_key,
        settings=settings,
        policy=policy,
    )

    assert result.tokens_found >= 1
    assert result.tokens_resolved >= 1
    assert result.tokens_expired == 0
    assert result.tokens_failed == 0
    assert result.policy_gate == "allowed"
    # The resolved text should contain the original secret
    assert _SECRET_SK in result.resolved_text
    assert "Here is a key:" in result.resolved_text
    assert "end" in result.resolved_text


def test_resolve_tokens_disabled_settings():
    """Settings with vault disabled produces policy_gate='disabled'."""
    store = _make_store()
    vault_key = derive_vault_key("disabled-key")
    settings = _DisabledSettings()

    text = "Some text with [CIO:aabbcc]"
    result = resolve_tokens(
        text,
        store=store,
        vault_key=vault_key,
        settings=settings,
    )

    assert result.policy_gate == "disabled"
    assert result.tokens_found == 1
    assert result.tokens_resolved == 0
    assert result.tokens_denied == 1
    assert result.resolved_text == text  # unchanged


def test_resolve_tokens_denied_policy():
    """Policy with enabled=False produces policy_gate='denied_policy'."""
    store = _make_store()
    vault_key = derive_vault_key("denied-key")
    settings = _Settings()
    policy = _PolicyConstraints(_DisabledPolicy())

    text = "Some text with [CIO:aabbcc]"
    result = resolve_tokens(
        text,
        store=store,
        vault_key=vault_key,
        settings=settings,
        policy=policy,
    )

    assert result.policy_gate == "denied_policy"
    assert result.tokens_found == 1
    assert result.tokens_resolved == 0
    assert result.tokens_denied == 1
    assert result.resolved_text == text


def test_resolve_tokens_denied_app():
    """Policy with allowed_apps={'Terminal'} and dest_app='Safari' produces 'denied_app'."""
    store = _make_store()
    vault_key = derive_vault_key("denied-app-key")
    settings = _Settings()
    policy = _PolicyConstraints(_DeniedAppPolicy())

    text = "Some text with [CIO:aabbcc]"
    result = resolve_tokens(
        text,
        store=store,
        vault_key=vault_key,
        settings=settings,
        policy=policy,
        dest_app="Safari",
    )

    assert result.policy_gate == "denied_app"
    assert result.tokens_found == 1
    assert result.tokens_resolved == 0
    assert result.tokens_denied == 1
    assert result.resolved_text == text


def test_resolve_tokens_allowed_app():
    """Policy with allowed_apps={'Terminal'} and dest_app='Terminal' resolves successfully."""
    store = _make_store()
    vault_key = derive_vault_key("allowed-app-key")
    settings = _Settings()
    policy = _PolicyConstraints(_DeniedAppPolicy())

    # First create a real vault entry
    original_text = f"secret: {_SECRET_SK}"
    redacted, token_ids, _ = redact_text_with_tokens(
        original_text, store=store, vault_key=vault_key,
    )

    assert _SECRET_SK not in redacted

    result = resolve_tokens(
        redacted,
        store=store,
        vault_key=vault_key,
        settings=settings,
        policy=policy,
        dest_app="Terminal",
    )

    assert result.policy_gate == "allowed"
    assert result.tokens_resolved >= 1
    assert _SECRET_SK in result.resolved_text


def test_resolve_tokens_requires_approval():
    """Policy.requires_approval=True produces policy_gate='requires_approval'."""
    store = _make_store()
    vault_key = derive_vault_key("approval-key")
    settings = _Settings()
    policy = _PolicyConstraints(_ApprovalPolicy())

    text = "Some text with [CIO:aabbcc]"
    result = resolve_tokens(
        text,
        store=store,
        vault_key=vault_key,
        settings=settings,
        policy=policy,
    )

    assert result.policy_gate == "requires_approval"
    assert result.tokens_found == 1
    assert result.tokens_resolved == 0
    assert result.tokens_denied == 1
    assert result.resolved_text == text


def test_resolve_tokens_no_tokens_in_text():
    """resolve_tokens on text without tokens returns tokens_found=0."""
    store = _make_store()
    vault_key = derive_vault_key("no-tokens-key")
    settings = _Settings()
    policy = _PolicyConstraints(_BackfillPolicy())

    text = "This is normal text with no vault tokens."
    result = resolve_tokens(
        text,
        store=store,
        vault_key=vault_key,
        settings=settings,
        policy=policy,
    )

    assert result.tokens_found == 0
    assert result.tokens_resolved == 0
    assert result.tokens_expired == 0
    assert result.tokens_failed == 0
    assert result.policy_gate == "allowed"
    assert result.resolved_text == text


def test_resolve_tokens_expired_token():
    """Looking up a token that does not exist in vault increments tokens_expired."""
    store = _make_store()
    vault_key = derive_vault_key("expired-key")
    settings = _Settings()
    policy = _PolicyConstraints(_BackfillPolicy())

    # Fabricate text with a vault token that has no corresponding vault entry
    text = "Here is a token [CIO:ff0011] that does not exist in the vault."
    result = resolve_tokens(
        text,
        store=store,
        vault_key=vault_key,
        settings=settings,
        policy=policy,
    )

    assert result.tokens_found == 1
    assert result.tokens_resolved == 0
    assert result.tokens_expired == 1
    assert result.tokens_failed == 0
    assert result.policy_gate == "allowed"
    # Text remains unchanged since token could not be resolved
    assert "[CIO:ff0011]" in result.resolved_text
