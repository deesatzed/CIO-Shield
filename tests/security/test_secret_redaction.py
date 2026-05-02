import re

from cognitiveio.security.redaction import redact_payload, redact_text


def test_redact_text_hides_alias_and_secret_values():
    raw = "token={{SECRET:OPENAI_API_KEY}} api_key=sk-abcdefghijklmnopqrstuvwx"
    out = redact_text(raw)
    assert "{{SECRET:OPENAI_API_KEY}}" not in out
    assert "[REDACTED_SECRET]" in out
    assert "sk-abcdefghijklmnopqrstuvwx" not in out


def test_redact_payload_hides_sensitive_keys():
    payload = {
        "candidate_id": "c1",
        "token": "secret-value",
        "nested": {"api_key": "sk-example", "note": "ok"},
    }
    out = redact_payload(payload)
    assert out["token"] == "[REDACTED_SECRET]"
    assert out["nested"]["api_key"] == "[REDACTED_SECRET]"
    assert out["nested"]["note"] == "ok"


def test_redact_text_with_extra_patterns():
    """extra_patterns parameter adds corporate-specific redaction rules."""
    corporate_patterns = [re.compile(r"ACME_TOKEN_[A-Z0-9]{8,}")]
    raw = "config=ACME_TOKEN_ABCDEF1234 and note=hello"
    out = redact_text(raw, extra_patterns=corporate_patterns)
    assert "ACME_TOKEN_ABCDEF1234" not in out
    assert "[REDACTED_SECRET]" in out
    assert "hello" in out


def test_redact_text_extra_patterns_no_match():
    """extra_patterns that don't match leave text unchanged."""
    corporate_patterns = [re.compile(r"NOMATCH_[A-Z]{50}")]
    raw = "clean text here"
    out = redact_text(raw, extra_patterns=corporate_patterns)
    assert out == "clean text here"


def test_redact_payload_with_extra_patterns():
    """redact_payload passes extra_patterns through to redact_text."""
    corporate_patterns = [re.compile(r"CORP_KEY_[A-Z0-9]{10,}")]
    payload = {
        "note": "use CORP_KEY_ABCDEF123456 for auth",
        "nested": ["CORP_KEY_ZYXWVU098765"],
    }
    out = redact_payload(payload, extra_patterns=corporate_patterns)
    assert "CORP_KEY_ABCDEF123456" not in out["note"]
    assert "CORP_KEY_ZYXWVU098765" not in out["nested"][0]


# ---------------------------------------------------------------------------
# Built-in pattern library tests
# ---------------------------------------------------------------------------


class TestBuiltinPatterns:
    """Verify every pattern in patterns.json detects its target."""

    def test_patterns_loaded(self):
        from cognitiveio.security.redaction import SECRET_VALUE_PATTERNS
        assert len(SECRET_VALUE_PATTERNS) >= 15

    def test_openai_key(self):
        assert "[REDACTED_SECRET]" in redact_text("key: sk-abc123defghijklmnopqrstuvwx")

    def test_aws_key(self):
        assert "[REDACTED_SECRET]" in redact_text("AKIAIOSFODNN7EXAMPLE")

    def test_generic_label(self):
        assert "[REDACTED_SECRET]" in redact_text("api_key=myvalue123")

    def test_private_key_header(self):
        assert "[REDACTED_SECRET]" in redact_text("-----BEGIN RSA PRIVATE KEY-----")

    def test_email(self):
        assert "[REDACTED_SECRET]" in redact_text("contact user@example.com now")

    def test_phone(self):
        assert "[REDACTED_SECRET]" in redact_text("call +1 555 123 4567 today")

    def test_iban(self):
        assert "[REDACTED_SECRET]" in redact_text("pay to DE89370400440532013000")

    def test_credit_card_16(self):
        assert "[REDACTED_SECRET]" in redact_text("card 4111 1111 1111 1111")

    def test_credit_card_amex(self):
        assert "[REDACTED_SECRET]" in redact_text("amex 3782 822463 10005")

    def test_ipv4(self):
        assert "[REDACTED_SECRET]" in redact_text("host 192.168.1.1 is up")

    def test_ipv6(self):
        assert "[REDACTED_SECRET]" in redact_text("addr 2001:0db8:85a3:0000:0000:8a2e:0370:7334")

    def test_mac_address(self):
        assert "[REDACTED_SECRET]" in redact_text("mac 00:1A:2B:3C:4D:5E")

    def test_us_ssn(self):
        assert "[REDACTED_SECRET]" in redact_text("ssn 123-45-6789")

    def test_uk_nino(self):
        assert "[REDACTED_SECRET]" in redact_text("nino AB 12 34 56 C")

    def test_jwt(self):
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        assert "[REDACTED_SECRET]" in redact_text(f"bearer {token}")

    def test_github_token(self):
        assert "[REDACTED_SECRET]" in redact_text(
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        )

    def test_stripe_key(self):
        # Constructed at runtime to avoid GitHub push protection false positive
        fake_key = "sk_live_" + "x" * 24
        assert "[REDACTED_SECRET]" in redact_text(fake_key)

    def test_eth_address(self):
        assert "[REDACTED_SECRET]" in redact_text(
            "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"
        )

    def test_btc_address_bech32(self):
        assert "[REDACTED_SECRET]" in redact_text(
            "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        )

    def test_ltc_address(self):
        assert "[REDACTED_SECRET]" in redact_text(
            "ltc1qw508d6qejxtdg4y5r3zarvary0c5xw7kgmn4n9"
        )

    def test_crypto_labeled(self):
        assert "[REDACTED_SECRET]" in redact_text(
            "BTC: bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        )

    def test_clean_text_unchanged(self):
        assert redact_text("Hello world, normal text here.") == "Hello world, normal text here."

    def test_empty_text_unchanged(self):
        assert redact_text("") == ""


class TestPatternLoading:
    """Verify the JSON loading mechanism."""

    def test_get_builtin_patterns_returns_list(self):
        from cognitiveio.security.redaction import get_builtin_patterns
        patterns = get_builtin_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) >= 15

    def test_get_builtin_patterns_returns_copy(self):
        """Modifying the returned list does not affect the module-level list."""
        from cognitiveio.security.redaction import (
            SECRET_VALUE_PATTERNS,
            get_builtin_patterns,
        )
        patterns = get_builtin_patterns()
        original_len = len(SECRET_VALUE_PATTERNS)
        patterns.append(re.compile(r"EXTRA"))
        assert len(SECRET_VALUE_PATTERNS) == original_len
