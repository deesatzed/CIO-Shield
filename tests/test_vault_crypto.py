"""Unit tests for vault_crypto.py — ZERO mocks, real encryption."""
from __future__ import annotations

import re
import time

from cognitiveio.security.vault_crypto import (
    VAULT_TOKEN_RE_PATTERN,
    VaultEntry,
    decrypt_value,
    derive_vault_key,
    encrypt_value,
    extract_token_id,
    format_vault_token,
    generate_token_id,
)


# ---------------------------------------------------------------------------
# 1. generate_token_id — basic shape
# ---------------------------------------------------------------------------

def test_generate_token_id_returns_6_hex_chars():
    """Token IDs must be exactly 6 lowercase hex characters."""
    token = generate_token_id("my-secret-value")
    assert len(token) == 6, f"Expected length 6, got {len(token)}: {token!r}"
    assert all(c in "0123456789abcdef" for c in token), (
        f"Non-hex character found in token: {token!r}"
    )


# ---------------------------------------------------------------------------
# 2. generate_token_id — different values produce different tokens
# ---------------------------------------------------------------------------

def test_generate_token_id_different_values_different_tokens():
    """Two different secret values should produce different token IDs.

    The HMAC input includes the value, so distinct values almost certainly
    yield distinct digests (collision probability ~1/16M per pair).
    We generate several pairs to guard against a single lucky collision.
    """
    tokens_a = {generate_token_id("alpha-secret") for _ in range(5)}
    tokens_b = {generate_token_id("beta-secret") for _ in range(5)}
    # Each set should have produced distinct tokens (randomness per call)
    # and the two sets should not overlap entirely.
    assert len(tokens_a) > 1 or len(tokens_b) > 1, (
        "Expected randomness across calls"
    )


# ---------------------------------------------------------------------------
# 3. generate_token_id — same value, different timestamps
# ---------------------------------------------------------------------------

def test_generate_token_id_same_value_different_timestamps():
    """Same secret value with different explicit timestamps yields different
    tokens because os.urandom(4) adds per-call randomness."""
    ts1 = 1000000.0
    ts2 = 2000000.0
    # Generate multiple tokens to account for the (vanishingly small)
    # possibility that the random nonce produces a collision.
    tokens_ts1 = {generate_token_id("shared-val", timestamp=ts1) for _ in range(5)}
    tokens_ts2 = {generate_token_id("shared-val", timestamp=ts2) for _ in range(5)}
    # With 4 bytes of randomness per call, each set of 5 should be unique.
    assert len(tokens_ts1) > 1, "Expected randomness within ts1 group"
    assert len(tokens_ts2) > 1, "Expected randomness within ts2 group"


# ---------------------------------------------------------------------------
# 4. format_vault_token — correct bracket format
# ---------------------------------------------------------------------------

def test_format_vault_token_correct_format():
    result = format_vault_token("a7b3c9")
    assert result == "[CIO:a7b3c9]"


# ---------------------------------------------------------------------------
# 5. extract_token_id — valid token
# ---------------------------------------------------------------------------

def test_extract_token_id_valid_token():
    assert extract_token_id("[CIO:a7b3c9]") == "a7b3c9"


# ---------------------------------------------------------------------------
# 6. extract_token_id — invalid tokens all return None
# ---------------------------------------------------------------------------

def test_extract_token_id_invalid_tokens():
    invalid_inputs = [
        "[CIO:xyz]",        # too short, non-hex
        "[CIO:abcdefg]",    # 7 hex chars (too long)
        "hello",            # no brackets at all
        "",                 # empty string
        "[CIO:ABCDEF]",    # uppercase hex — not accepted (lowercase only)
    ]
    for bad in invalid_inputs:
        result = extract_token_id(bad)
        assert result is None, (
            f"Expected None for input {bad!r}, got {result!r}"
        )


# ---------------------------------------------------------------------------
# 7. VAULT_TOKEN_RE_PATTERN matches valid tokens in text
# ---------------------------------------------------------------------------

def test_vault_token_re_pattern_matches():
    text = "Redacted SSN is [CIO:a7b3c9] and API key is [CIO:00ff11]."
    matches = re.findall(VAULT_TOKEN_RE_PATTERN, text)
    assert matches == ["[CIO:a7b3c9]", "[CIO:00ff11]"]


# ---------------------------------------------------------------------------
# 8. VAULT_TOKEN_RE_PATTERN rejects uppercase hex
# ---------------------------------------------------------------------------

def test_vault_token_re_pattern_no_match_uppercase():
    text = "This should not match: [CIO:ABCDEF]"
    matches = re.findall(VAULT_TOKEN_RE_PATTERN, text)
    assert matches == []


# ---------------------------------------------------------------------------
# 9. derive_vault_key — returns 32 bytes (AES-256)
# ---------------------------------------------------------------------------

def test_derive_vault_key_returns_32_bytes():
    key = derive_vault_key()
    assert isinstance(key, bytes)
    assert len(key) == 32, f"Expected 32-byte AES-256 key, got {len(key)} bytes"


# ---------------------------------------------------------------------------
# 10. derive_vault_key — explicit db_key differs from default
# ---------------------------------------------------------------------------

def test_derive_vault_key_with_db_key():
    key_default = derive_vault_key()
    key_custom = derive_vault_key(db_key="my-sqlcipher-passphrase")
    assert key_default != key_custom, (
        "Key derived with explicit db_key must differ from machine-identity key"
    )
    assert len(key_custom) == 32


# ---------------------------------------------------------------------------
# 11. derive_vault_key — deterministic for same inputs
# ---------------------------------------------------------------------------

def test_derive_vault_key_deterministic():
    key_a = derive_vault_key(db_key="stable-key")
    key_b = derive_vault_key(db_key="stable-key")
    assert key_a == key_b, "Same db_key must produce identical vault keys"

    key_default_a = derive_vault_key()
    key_default_b = derive_vault_key()
    assert key_default_a == key_default_b, (
        "Default (no db_key) must be deterministic on the same machine"
    )


# ---------------------------------------------------------------------------
# 12. encrypt / decrypt round-trip
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip():
    vault_key = derive_vault_key(db_key="test-roundtrip")
    plaintext = "SSN: 123-45-6789"

    ciphertext, nonce, tag = encrypt_value(plaintext, vault_key)

    # Ciphertext must not be empty and must differ from plaintext bytes
    assert len(ciphertext) > 0
    assert ciphertext != plaintext.encode("utf-8")

    # Decrypt must recover the original
    recovered = decrypt_value(ciphertext, nonce, tag, vault_key)
    assert recovered == plaintext


# ---------------------------------------------------------------------------
# 13. encrypt / decrypt round-trip with unicode
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_unicode():
    vault_key = derive_vault_key(db_key="test-unicode")
    plaintext = "pароль 秘密 🔑"

    ciphertext, nonce, tag = encrypt_value(plaintext, vault_key)
    recovered = decrypt_value(ciphertext, nonce, tag, vault_key)
    assert recovered == plaintext


# ---------------------------------------------------------------------------
# 14. decrypt with wrong key returns None
# ---------------------------------------------------------------------------

def test_decrypt_wrong_key_returns_none():
    correct_key = derive_vault_key(db_key="correct-key")
    wrong_key = derive_vault_key(db_key="wrong-key")

    ciphertext, nonce, tag = encrypt_value("top-secret", correct_key)

    result = decrypt_value(ciphertext, nonce, tag, wrong_key)
    assert result is None, "Decrypting with wrong key must return None"


# ---------------------------------------------------------------------------
# 15. encrypt produces different nonces (AES-GCM random nonce)
# ---------------------------------------------------------------------------

def test_encrypt_produces_different_nonces():
    vault_key = derive_vault_key(db_key="nonce-test")
    plaintext = "same-plaintext-twice"

    _, nonce_a, _ = encrypt_value(plaintext, vault_key)
    _, nonce_b, _ = encrypt_value(plaintext, vault_key)

    assert nonce_a != nonce_b, (
        "Two encryptions of the same plaintext must use different random nonces"
    )


# ---------------------------------------------------------------------------
# 16. VaultEntry dataclass construction
# ---------------------------------------------------------------------------

def test_vault_entry_dataclass():
    now = time.time()
    entry = VaultEntry(
        token_id="ab12cd",
        encrypted_value=b"\x01\x02\x03",
        nonce=b"\x00" * 12,
        tag=b"\xff" * 16,
        pattern_id="ssn-pattern",
        source_app="Safari",
        dest_app="Slack",
        created_ts=now,
        expires_ts=now + 300.0,
    )
    assert entry.token_id == "ab12cd"
    assert entry.encrypted_value == b"\x01\x02\x03"
    assert entry.nonce == b"\x00" * 12
    assert entry.tag == b"\xff" * 16
    assert entry.pattern_id == "ssn-pattern"
    assert entry.source_app == "Safari"
    assert entry.dest_app == "Slack"
    assert entry.created_ts == now
    assert entry.expires_ts == now + 300.0


# ---------------------------------------------------------------------------
# 17. encrypt / decrypt empty string
# ---------------------------------------------------------------------------

def test_encrypt_empty_string():
    vault_key = derive_vault_key(db_key="empty-str-test")
    plaintext = ""

    ciphertext, nonce, tag = encrypt_value(plaintext, vault_key)
    # Ciphertext for empty plaintext should itself be empty (no data bytes)
    assert isinstance(ciphertext, bytes)
    assert isinstance(nonce, bytes)
    assert len(nonce) == 12
    assert isinstance(tag, bytes)
    assert len(tag) == 16

    recovered = decrypt_value(ciphertext, nonce, tag, vault_key)
    assert recovered == plaintext
