"""Vault cryptography — per-value AES-256-GCM encryption and token ID generation.

Tokens are HMAC-SHA256 derived, truncated to 6 hex chars. They are
meaningless outside the local vault and link redacted clipboard content
back to encrypted originals for authorized backfill.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Optional


# Vault token prefix used in redacted text: [CIO:a7b3c9]
VAULT_TOKEN_RE_PATTERN = r"\[CIO:[0-9a-f]{6}\]"

# Machine-local HMAC key derived from hostname + username
_HMAC_KEY: Optional[bytes] = None


def _get_hmac_key() -> bytes:
    """Derive a stable HMAC key from machine identity.

    This is NOT a secret — it's a deterministic seed for token generation.
    Security comes from the AES-256-GCM encryption of vault values, not
    from token unpredictability.
    """
    global _HMAC_KEY
    if _HMAC_KEY is not None:
        return _HMAC_KEY
    identity = f"{os.uname().nodename}:{os.getlogin()}:cognitiveio-vault"
    _HMAC_KEY = hashlib.sha256(identity.encode()).digest()
    return _HMAC_KEY


def generate_token_id(secret_value: str, timestamp: float = 0.0) -> str:
    """Generate a 6-char hex token ID for a secret value.

    The token is HMAC-SHA256(machine_key, value + timestamp), truncated
    to 6 hex chars (16.7M possible values). Collisions are acceptable
    and handled by the vault lookup falling back to scanning.
    """
    ts = timestamp or time.time()
    msg = f"{secret_value}:{ts}:{os.urandom(4).hex()}".encode()
    digest = hmac.new(_get_hmac_key(), msg, hashlib.sha256).hexdigest()
    return digest[:6]


def format_vault_token(token_id: str) -> str:
    """Format a token ID as a redaction placeholder: [CIO:a7b3c9]"""
    return f"[CIO:{token_id}]"


def extract_token_id(token_str: str) -> Optional[str]:
    """Extract the 6-char hex ID from a vault token string.

    Returns None if the string is not a valid vault token.
    """
    if token_str.startswith("[CIO:") and token_str.endswith("]") and len(token_str) == 12:
        candidate = token_str[5:11]
        if all(c in "0123456789abcdef" for c in candidate):
            return candidate
    return None


@dataclass
class VaultEntry:
    """A single vault entry mapping token to encrypted original."""
    token_id: str
    encrypted_value: bytes
    nonce: bytes
    tag: bytes
    pattern_id: str
    source_app: str
    dest_app: str
    created_ts: float
    expires_ts: float


def derive_vault_key(db_key: Optional[str] = None) -> bytes:
    """Derive a 32-byte AES key for vault value encryption.

    If a db_key is provided (from SQLCipher config), derive from it.
    Otherwise derive from machine identity (defense-in-depth with SQLCipher).
    """
    if db_key:
        return hashlib.sha256(f"vault:{db_key}".encode()).digest()
    identity = f"{os.uname().nodename}:{os.getlogin()}:cognitiveio-vault-key"
    return hashlib.sha256(identity.encode()).digest()


def encrypt_value(plaintext: str, vault_key: bytes) -> tuple[bytes, bytes, bytes]:
    """Encrypt a secret value with AES-256-GCM.

    Returns (ciphertext, nonce, tag).
    Uses Python's built-in cryptography via the 'cryptography' library
    if available, otherwise falls back to a simpler XOR-based approach
    that still provides the vault token linkage (defense in depth with SQLCipher).
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        aesgcm = AESGCM(vault_key)
        ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        # AESGCM appends the 16-byte tag to ciphertext
        ciphertext = ciphertext_and_tag[:-16]
        tag = ciphertext_and_tag[-16:]
        return ciphertext, nonce, tag
    except ImportError:
        # Fallback: XOR with key-derived stream + HMAC tag
        # This is NOT as secure as AES-GCM but provides vault linkage
        # when cryptography library is unavailable. SQLCipher provides
        # the primary encryption layer.
        nonce = os.urandom(12)
        plainbytes = plaintext.encode("utf-8")
        stream = hashlib.sha256(vault_key + nonce).digest()
        # Extend stream to cover plaintext length
        while len(stream) < len(plainbytes):
            stream += hashlib.sha256(stream).digest()
        ciphertext = bytes(a ^ b for a, b in zip(plainbytes, stream))
        tag = hmac.new(vault_key, nonce + ciphertext, hashlib.sha256).digest()[:16]
        return ciphertext, nonce, tag


def decrypt_value(ciphertext: bytes, nonce: bytes, tag: bytes, vault_key: bytes) -> Optional[str]:
    """Decrypt a vault value. Returns None if decryption fails (tampered/wrong key)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(vault_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
        return plaintext.decode("utf-8")
    except ImportError:
        # Fallback: XOR decryption with HMAC verification
        expected_tag = hmac.new(vault_key, nonce + ciphertext, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expected_tag):
            return None
        stream = hashlib.sha256(vault_key + nonce).digest()
        while len(stream) < len(ciphertext):
            stream += hashlib.sha256(stream).digest()
        plainbytes = bytes(a ^ b for a, b in zip(ciphertext, stream))
        try:
            return plainbytes.decode("utf-8")
        except UnicodeDecodeError:
            return None
    except Exception:
        return None
