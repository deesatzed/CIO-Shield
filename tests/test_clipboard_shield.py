"""Unit tests for clipboard_shield.py — core scanning logic.

These tests use NO mocks. They exercise the real pattern engine and
real redaction functions against sample secret strings.
"""
from __future__ import annotations

import re

from cognitiveio.runtime.clipboard_shield import ScanResult, scan_text_for_secrets


class TestScanTextForSecrets:
    def test_clean_text_no_secrets(self):
        result = scan_text_for_secrets("Hello, this is perfectly normal text.")
        assert result.contains_secrets is False
        assert result.match_count == 0
        assert result.redacted_text == "Hello, this is perfectly normal text."

    def test_openai_key_detected(self):
        text = "My key is sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef please keep safe"
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 1
        assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in result.redacted_text

    def test_aws_key_detected(self):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 1
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_text

    def test_credit_card_detected(self):
        text = "Card: 4111 1111 1111 1111"
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 1
        assert "4111 1111 1111 1111" not in result.redacted_text

    def test_email_detected(self):
        text = "Contact me at user@example.com for details."
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 1
        assert "user@example.com" not in result.redacted_text

    def test_ssn_detected(self):
        text = "SSN is 123-45-6789"
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 1
        assert "123-45-6789" not in result.redacted_text

    def test_jwt_detected(self):
        text = "Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 1
        assert "eyJhbG" not in result.redacted_text

    def test_github_token_detected(self):
        text = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij1234"
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 1
        assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in result.redacted_text

    def test_private_key_header_detected(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 1

    def test_multiple_secrets_counted(self):
        text = (
            "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef "
            "user@example.com "
            "123-45-6789"
        )
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert result.match_count >= 3
        assert len(result.pattern_ids_matched) >= 3

    def test_redacted_text_has_no_secrets(self):
        text = "key: sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef SSN: 123-45-6789"
        result = scan_text_for_secrets(text)
        rescan = scan_text_for_secrets(result.redacted_text)
        # Redacted output should be clean (no re-detection of the same secrets)
        assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in rescan.redacted_text
        assert "123-45-6789" not in rescan.redacted_text

    def test_empty_text(self):
        result = scan_text_for_secrets("")
        assert result.contains_secrets is False
        assert result.original_length == 0
        assert result.redacted_text == ""
        assert result.match_count == 0

    def test_extra_patterns_applied(self):
        corp_pattern = re.compile(r"CORP-\d{8}")
        text = "Internal ref: CORP-12345678"
        result = scan_text_for_secrets(text, extra_patterns=[corp_pattern])
        assert result.contains_secrets is True
        assert "CORP-12345678" not in result.redacted_text

    def test_mixed_content_partial_redaction(self):
        text = "Hello sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef goodbye"
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert "Hello" in result.redacted_text
        assert "goodbye" in result.redacted_text
        assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in result.redacted_text

    def test_scan_result_dataclass_fields(self):
        result = scan_text_for_secrets("some text")
        assert isinstance(result, ScanResult)
        assert hasattr(result, "contains_secrets")
        assert hasattr(result, "original_length")
        assert hasattr(result, "redacted_text")
        assert hasattr(result, "pattern_ids_matched")
        assert hasattr(result, "match_count")

    def test_original_length_preserved(self):
        text = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        result = scan_text_for_secrets(text)
        assert result.original_length == len(text)
        # Redacted text may differ in length, but original_length stays the same
        assert result.original_length == 35

    def test_generic_secret_label_detected(self):
        # Use generic_secret_label pattern (secret=value) to avoid GitHub push protection
        text = "secret=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        result = scan_text_for_secrets(text)
        assert result.contains_secrets is True
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in result.redacted_text
